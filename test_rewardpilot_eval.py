"""Golden tool evaluation. Default is offline and never writes the wallet.

Run: python test_rewardpilot_eval.py
Optional live embedding/Pinecone checks: python test_rewardpilot_eval.py --live-policy
Exit 1 means a golden expectation failed, including documented coverage gaps.
No model is invoked: tool selection and generated-prose hallucinations are N/A.
"""
import argparse
from collections import defaultdict
from contextlib import ExitStack
import json
from math import isclose
from pathlib import Path
from unittest.mock import patch

import agent_tools
from decision_engine import get_reward_value

ROOT = Path(__file__).resolve().parent


def golden_cash(case, catalog, valuations):
    """Independent oracle: intended categories in cases, rates only from JSON."""
    rows = {}
    for card_id, category in case['expected']['categories'].items():
        card = catalog[card_id]
        rule = next(rule for rule in card['earn_rules'] if rule['category'] == category)
        amount = case['purchase']['amount'] * rule['rate']
        if rule['unit'] == 'percent_cashback':
            amount /= 100
            value = amount
        else:
            cpp = valuations.get(card['reward_program'], {}).get('cents_per_point')
            value = None if cpp is None else amount * cpp / 100
        rows[card_id] = (category, amount, value)
    return rows


def run_evaluation(live_policy=False):
    data = json.loads((ROOT / 'data/eval_cases.json').read_text(encoding='utf-8'))
    catalog = {c['card_id']: c for c in json.loads((ROOT / 'data/card_catalog.json').read_text())}
    valuations = json.loads((ROOT / 'data/reward_valuations.json').read_text())
    metrics = defaultdict(lambda: [0, 0])
    failures, pending, observations = [], [], []

    def check(case, metric, condition, reason):
        metrics[metric][1] += 1
        metrics[metric][0] += bool(condition)
        if not condition:
            failures.append((case['case_id'], reason))

    for case in data['cases']:
        expected = case['expected']
        purchase = case['purchase']
        trace, results = [], {}
        def invoke(name, args):
            trace.append(name)
            return getattr(agent_tools, name).invoke(args)
        try:
            with ExitStack() as stack:
                # Patch read boundaries only; calculations and tool implementations are real.
                stack.enter_context(patch.object(agent_tools, 'get_user_cards', return_value=case['wallet']['card_ids']))
                stack.enter_context(patch.object(agent_tools, 'get_reward_balances', return_value=case['wallet']['reward_balances']))
                if not live_policy:
                    stack.enter_context(patch.object(agent_tools, 'retrieve_policy_context', side_effect=RuntimeError('Live retrieval disabled')))
                wallet = invoke('get_rewards_wallet', {'user_id':case['user_id']})
                rows = invoke('compare_cash_payment', {'user_id':case['user_id'], 'amount':purchase['amount'],
                    'purchase_type':purchase['type'], 'merchant':purchase['merchant'], 'booking_channel':purchase['booking_channel'],
                    **{key: purchase[key] for key in ('purchase_method', 'prime_member', 'prepaid', 'is_us_supermarket', 'online_grocery_eligible') if key in purchase}})
                results['cash'] = rows
                oracle = golden_cash(case, catalog, valuations)
                values = [v[2] for v in oracle.values() if v[2] is not None]
                winners = {k for k,v in oracle.items() if v[2] == max(values)} if values else set()
                check(case, 'Cash selection', bool(rows) and rows[0]['card_id'] in winners,
                      f"Cash winner {rows[0]['card_id'] if rows else None}; expected one of {sorted(winners)}")
                check(case, 'Golden consistency', expected['cash_winner'] in winners,
                      'Dataset winner conflicts with current configured values; review golden case')
                check(case, 'Wallet compliance', bool(rows) and {r['card_id'] for r in rows} == set(wallet['card_ids']),
                      'Cash results omitted owned cards or included unowned cards')
                numeric_ok = len(rows) == len(oracle)
                for row in rows:
                    category, amount, value = oracle[row['card_id']]
                    actual_value = (row.get('reward_value') or {}).get('estimated_value_usd')
                    numeric_ok &= row['mapped_category'] == category and isclose(row['reward_amount'], amount)
                    numeric_ok &= (actual_value is None if value is None else
                                   actual_value is not None and isclose(actual_value, value))
                check(case, 'Cash rules and values', numeric_ok, 'Mapped category, earned amount, or USD value differs from catalog golden expectation')
                award = case['award']
                if award:
                    args = {'user_id':case['user_id'], 'cash_price':purchase['amount'], **award}
                    if expected.get('award_rejected'):
                        try:
                            invoke('evaluate_points_redemption', args)
                        except (ValueError, TypeError):
                            rejected = True
                        else:
                            rejected = False
                        check(case, 'Input validation', rejected, 'Missing award quote accepted')
                    else:
                        result = invoke('evaluate_points_redemption', args)
                        results['award'] = result
                        feasible = result['can_book_directly'] or any(p['can_cover_shortfall'] for p in result['transfer_options'])
                        check(case, 'Award feasibility', feasible == expected['points_feasible'] and
                              result['shortfall'] == expected['shortfall'] and result['can_book_directly'] == expected['can_book_directly'],
                              'Award coverage or shortfall incorrect')
                        paths = [{k:p[k] for k in ('from_program','required_transfer','can_cover_shortfall','ratio')} for p in result['transfer_options']]
                        check(case, 'Transfer path', paths == expected['transfer_paths'], 'Transfer paths differ from golden expectation')
                        check(case, 'Quote preservation', result['required_points'] == award['required_points'] and
                              result['taxes_fees'] == award['taxes_fees'], 'Quote changed or discount applied')
                        if 'redemption_cpp' in expected:
                            check(case, 'Redemption value', result['cents_per_point'] == expected['redemption_cpp'], 'Redemption CPP incorrect')
                        if expected.get('valuation_missing'):
                            check(case, 'Missing valuation', get_reward_value(award['target_program'], award['required_points']) is None,
                                  'Expected unvalued currency now has valuation; review golden case')
                if 'policy' in case:
                    if live_policy:
                        evidence = invoke('search_rewards_policy', case['policy'])
                        correct = not evidence if expected.get('empty_evidence') else bool(evidence) and evidence[0]['source_file'] == expected['expected_policy_source']
                        check(case, 'Policy retrieval', correct, 'Wrong top policy source or unexpected evidence')
                    elif expected.get('empty_evidence'):
                        # Boundary contract only: NOT a retrieval or LLM hallucination score.
                        with patch.object(agent_tools, 'retrieve_policy_context', return_value=[]):
                            evidence = invoke('search_rewards_policy', case['policy'])
                        check(case, 'Empty-evidence contract', evidence == [], 'Policy tool invented evidence from an empty retrieval')
                        pending.append(case['case_id'])
                    else:
                        evidence = None
                        pending.append(case['case_id'])
                    if evidence is not None:
                        results['policy'] = evidence
                        text = json.dumps(evidence, ensure_ascii=False).lower()
                        check(case, 'Evidence content checks', all(s.lower() in text for s in expected['must_contain']) and
                              all(s.lower() not in text for s in expected['must_not_contain']), 'Required policy facts missing or forbidden claim/source present')
                elif expected['must_not_contain']:
                    text = json.dumps(results).lower()
                    check(case, 'Structured claim checks', all(s.lower() not in text for s in expected['must_not_contain']), 'Forbidden unowned card in structured results')
                planned = [name for name in expected['expected_tools'] if name != 'search_rewards_policy' or
                           live_policy or expected.get('empty_evidence')]
                check(case, 'Tool contract execution', trace == planned, f'Tool trace {trace} differs from evaluation plan {planned}')
                observations.append({'case_id':case['case_id'], 'tools_called':trace, 'results':results})
        except Exception as error:
            failures.append((case['case_id'], f'{type(error).__name__}: {error}'))
    print('\n## RewardPilot Evaluation\n')
    print(f"Cases: {len(data['cases'])}")
    for label, (passed,total) in metrics.items():
        print(f'{label}: {passed}/{total}')
    if not live_policy:
        print(f'Policy retrieval: not measured offline ({len(pending)} live cases pending)')
    print('Tool-selection accuracy: N/A (runner invokes tools; no agent chooses them)')
    print('Generated-response hallucinations: N/A (no Nebius chat calls)')
    claim_metrics = ('Structured claim checks', 'Empty-evidence contract', 'Evidence content checks')
    unsupported = sum(metrics[name][1] - metrics[name][0] for name in claim_metrics)
    print(f'Unsupported structured claims / evidence-check failures: {unsupported} (not a prose hallucination score)')
    print(f'Failed cases: {len({case for case,_ in failures})}')
    for case_id, reason in failures:
        print(f'FAIL {case_id}: {reason}')
    for case in data['cases']:
        if case.get('known_gap'):
            print(f"COVERAGE {case['case_id']}: {case['known_gap']}")
    if pending:
        print('Live retrieval pending: ' + ', '.join(pending))
    return {'metrics':dict(metrics), 'failures':failures, 'observations':observations, 'pending_live':pending}


def test_golden_evaluation():
    report = run_evaluation()
    assert not report['failures'], report['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-policy', action='store_true', help='Opt in to paid Nebius embeddings and Pinecone retrieval, without an LLM agent')
    args = parser.parse_args()
    raise SystemExit(bool(run_evaluation(args.live_policy)['failures']))
