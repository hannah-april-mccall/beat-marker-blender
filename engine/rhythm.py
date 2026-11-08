"""Conservative beat-grid recovery from stable sections of the full recording.

This estimates musical timing, not certainty. Variable-tempo material is left alone
in automatic mode. A steady-grid request is explicit and retains the raw results.
"""
from copy import deepcopy
import math
import numpy as np

VERSION = 'steady-recovery-1'

def fit_reference(rows):
    times = np.asarray([r['time'] for r in rows], dtype=float)
    if len(times) < 18:
        return None, 'Too few detected beats for a stable reference.'
    gaps = np.diff(times)
    windows = []
    width = 16
    for start in range(len(gaps) - width + 1):
        sample = gaps[start:start + width]
        median = float(np.median(sample))
        if not .25 <= median <= 1.34:
            continue
        if np.std(sample) / median > .03 or np.max(np.abs(sample / median - 1)) > .095:
            continue
        period = float(np.polyfit(np.arange(width + 1), times[start:start + width + 1], 1)[0])
        windows.append((start, period))
    if not windows:
        return None, 'No sufficiently stable later section was found.'
    # Select the dominant tempo among stable windows, rather than trusting the intro.
    candidates = []
    for _, period in windows:
        group = [(i, p) for i, p in windows if abs(p / period - 1) < .02]
        indices = sorted({j for i, _ in group for j in range(i, i + width + 1)})
        candidates.append((len(indices), group, indices))
    _, group, indices = max(candidates, key=lambda x: x[0])
    if len(indices) < 24:
        return None, 'The stable reference is too short to extrapolate reliably.'
    period = float(np.median([p for _, p in group]))
    stable_times = times[indices]
    tolerance = max(.025, period * .065)
    # Robust phase selection ignores strong syncopation and half-beat false positives.
    choices = []
    for seed in stable_times:
        numbers = np.rint((stable_times - seed) / period)
        residuals = np.abs(stable_times - (seed + numbers * period))
        choices.append((int(np.sum(residuals <= tolerance)), float(seed)))
    _, seed = max(choices)
    numbers = np.rint((stable_times - seed) / period)
    inliers = np.abs(stable_times - (seed + numbers * period)) <= tolerance
    intercept = seed
    for _ in range(4):
        period, intercept = map(float, np.polyfit(numbers[inliers], stable_times[inliers], 1))
        residuals = np.abs(stable_times - (intercept + numbers * period))
        inliers = residuals <= tolerance
    if np.sum(inliers) < 24 or period <= 0:
        return None, 'The reference does not have a consistent beat phase.'
    accepted = np.asarray(indices)[inliers]
    stable_mask = np.zeros(len(times), dtype=bool)
    stable_mask[accepted] = True
    # A few isolated detected beats must not make an expressive performance look rigid.
    ratios = gaps / period
    multiples = np.array([.5, 1., 2., 3., 4.])
    compatible = np.min(np.abs(ratios[:, None] / multiples - 1), axis=1) <= .08
    phase_agreement = float(np.mean(inliers))
    tempo_agreement = float(np.mean(compatible))
    stable_fraction = float(np.mean(stable_mask))
    window_spread = float(np.std([p for _, p in group]) / period)
    other_tempo_points = {j for i, p in windows if abs(p / period - 1) > .04 for j in range(i, i + width + 1)}
    competing_tempo = len(other_tempo_points) >= max(24, .10 * len(times))
    global_fit = tempo_agreement >= .85 and phase_agreement >= .90 and stable_fraction >= .20 and window_spread < .015 and not competing_tempo
    regions = []
    for value in times[accepted]:
        if not regions or value - regions[-1]['end'] > period * 1.5:
            regions.append({'start': float(value), 'end': float(value), 'beats': 1})
        else:
            regions[-1]['end'] = float(value)
            regions[-1]['beats'] += 1
    return {
        'period': period, 'intercept': intercept, 'bpm': 60 / period,
        'indices': accepted.tolist(), 'referenceStart': float(times[accepted[0]]),
        'referenceEnd': float(times[accepted[-1]]), 'referenceBeatCount': int(len(accepted)),
        'tempoAgreement': tempo_agreement, 'phaseAgreement': phase_agreement,
        'stableFraction': stable_fraction, 'globalFit': bool(global_fit),
        'competingTempoSections': bool(competing_tempo),
        'referenceRegions': regions,
    }, None

def meter_reference(rows, fit, requested='auto'):
    period, origin = fit['period'], fit['intercept']
    indices = fit['indices']
    slots = {int(round((rows[i]['time'] - origin) / period)) for i in indices}
    down_slots = {int(round((rows[i]['time'] - origin) / period))
                  for i in indices if rows[i].get('beat') == 1}
    if len(down_slots) < 3:
        return None, None, 0.0
    choices = []
    for meter in ([int(requested)] if requested != 'auto' else [2, 3, 4]):
        for phase in range(meter):
            expected = {n for n in slots if n % meter == phase}
            hits = len(expected & down_slots)
            precision = hits / len(down_slots)
            recall = hits / len(expected) if expected else 0
            score = 2 * precision * recall / (precision + recall) if precision + recall else 0
            choices.append((score, meter, phase))
    score, meter, phase = max(choices)
    if score < .65:
        return None, None, float(score)
    return meter, phase, float(score)

def recover(raw, mode='auto', meter='auto'):
    if mode not in ('auto', 'detected', 'steady'):
        raise ValueError('Unknown timing mode.')
    if str(meter) not in ('auto', '2', '3', '4'):
        raise ValueError('Choose Auto, 2, 3 or 4 beats per bar.')
    result = deepcopy(raw)
    result['schema'] = 2
    result['detectedBeats'] = deepcopy(raw['beats'])
    meta = {'version': VERSION, 'requestedMode': mode, 'requestedMeter': str(meter), 'applied': False,
            'inferredBeatCount': 0, 'inferredIntroBeatCount': 0}
    result['postAnalysis'] = meta
    if mode == 'detected':
        meta['message'] = 'Original model detections; no beat-grid recovery applied.'
        return result
    fit, reason = fit_reference(raw['beats'])
    if fit is None:
        meta['message'] = reason + ' Original detections retained.'
        return result
    meta.update({k: v for k, v in fit.items() if k != 'indices'})
    if mode == 'auto' and not fit['globalFit']:
        meta['message'] = 'A fixed pulse does not fit the full performance confidently. Original timing retained.'
        return result
    beats_per_bar, bar_phase, meter_score = meter_reference(raw['beats'], fit, str(meter))
    period, origin = fit['period'], fit['intercept']
    start = float(raw.get('activityStart', 0))
    end = min(float(raw.get('activityEnd', raw['duration'])), float(raw['duration']))
    first_slot = math.ceil((start - origin) / period - 1e-8)
    last_slot = math.floor((end - origin) / period + 1e-8)
    first_downbeat = (first_slot + (bar_phase - first_slot) % beats_per_bar) if beats_per_bar else None
    times = np.asarray([b['time'] for b in raw['beats']], dtype=float)
    snap = min(.045, period * .075)
    rows = []
    used_detections = set()
    for slot in range(first_slot, last_slot + 1):
        predicted = origin + slot * period
        if predicted < start and start - predicted < 1e-7:
            predicted = start
        nearest = int(np.argmin(np.abs(times - predicted)))
        detected = abs(times[nearest] - predicted) <= snap and start <= times[nearest] <= end
        at = float(times[nearest]) if detected else predicted
        if detected:
            used_detections.add(nearest)
        position = (slot - bar_phase) % beats_per_bar + 1 if beats_per_bar else None
        bar = (slot - first_downbeat) // beats_per_bar + 1 if beats_per_bar else None
        rows.append({'time': round(at, 8), 'beat': position, 'bar': bar,
                     'inferred': not bool(detected), 'gridTime': round(predicted, 8)})
    result['beats'] = rows
    result['medianBpm'] = fit['bpm']
    result['downbeatCount'] = sum(b['beat'] == 1 for b in rows)
    inferred = [b for b in rows if b['inferred']]
    meta.update({'applied': True, 'beatsPerBar': beats_per_bar, 'meterAgreement': meter_score,
                 'inferredBeatCount': len(inferred),
                 'inferredIntroBeatCount': sum(b['time'] < fit['referenceStart'] for b in inferred),
                 'discardedDetectionCount': len(times) - len(used_detections),
                 'message': 'Steady pulse recovered from later consistent beats. Inferred beats are marked in the beat map.'})
    return result
