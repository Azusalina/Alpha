/**
 * What the ball shows: how well the model fits ONE person (D68).
 *
 * The sphere is the person. Its surface is divided into one facet per model
 * parameter (13). Per facet the ball needs two numbers, both 0..1:
 *
 *  - `fit`   the ripples. How well the model has fitted the person on this
 *            facet; no evidence = 0 = a still surface.
 *  - `peak`  the spike. How concentrated that fit is: 0 = spread evenly over
 *            many statements, 1 = carried by a few strong ones.
 *  - `thin`  the fit rests on little evidence (draws the spike hollow).
 *
 * The back end does not produce these yet (front-back-communicate.md, request
 * for the ball); until it does the page shows `exampleFit()`, labelled as
 * example data. Nothing here is read from the model.
 */

import { PARAMETER_IDS, type ParameterId } from '../backend/types';

export interface Facet {
  id: ParameterId;
  fit: number;
  peak: number;
  thin: boolean;
}

export type BallFit = readonly Facet[];

/** Fixed facet directions: a Fibonacci sphere, so the parameter always sits in the same place. */
export function facetDirections(n = PARAMETER_IDS.length): [number, number, number][] {
  const out: [number, number, number][] = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * (i + 0.5)) / n;
    const r = Math.sqrt(1 - y * y);
    const a = i * 2.399963;
    out.push([Math.cos(a) * r, y, Math.sin(a) * r]);
  }
  return out;
}

/** A fixed, made-up fit: some facets strong, some spiked, one untouched. */
export function exampleFit(): BallFit {
  const fit = [0.82, 0.55, 0.7, 0.4, 0.62, 0.9, 0.3, 0.76, 0.45, 0.58, 0.68, 0.0, 0.35];
  const peak = [0.0, 0.7, 0.0, 0.0, 0.85, 0.0, 0.6, 0.0, 0.9, 0.0, 0.0, 0.0, 0.5];
  const thin = [false, false, false, false, false, false, true, false, true, false, false, false, true];
  return PARAMETER_IDS.map((id, i) => ({ id, fit: fit[i], peak: peak[i], thin: thin[i] }));
}
