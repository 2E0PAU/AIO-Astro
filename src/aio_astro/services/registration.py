"""Star-pair registration estimates a rigid transform without requiring solved WCS."""

from itertools import combinations

import numpy as np
from scipy.spatial import cKDTree


def register_stars(reference, current, *, maximum_rotation=5):
    reference, current = reference[:45], current[:45]
    if min(len(reference), len(current)) < 5:
        raise ValueError("Alignment needs at least five measured stars")
    ref_pairs = np.array(list(combinations(range(len(reference)), 2)))
    cur_pairs = np.array(list(combinations(range(len(current)), 2)))
    ref_vectors = reference[ref_pairs[:, 1]] - reference[ref_pairs[:, 0]]
    cur_vectors = current[cur_pairs[:, 1]] - current[cur_pairs[:, 0]]
    ref_lengths = np.linalg.norm(ref_vectors, axis=1)
    cur_lengths = np.linalg.norm(cur_vectors, axis=1)
    pair_tree = cKDTree(ref_lengths[:, None])
    star_tree = cKDTree(reference)
    best = None
    checked = 0
    for index in np.argsort(cur_lengths)[::-1]:
        if cur_lengths[index] < 20:
            continue
        nearby = pair_tree.query_ball_point([cur_lengths[index]], r=1.5)
        for candidate in nearby:
            if checked >= 1500:
                break
            for reverse in (False, True):
                vector = -ref_vectors[candidate] if reverse else ref_vectors[candidate]
                angle = np.arctan2(vector[1], vector[0]) - np.arctan2(
                    cur_vectors[index, 1], cur_vectors[index, 0]
                )
                angle = (angle + np.pi) % (2 * np.pi) - np.pi
                if abs(np.degrees(angle)) > maximum_rotation:
                    continue
                checked += 1
                rotation = np.array(
                    [[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]]
                )
                anchor = ref_pairs[candidate, int(reverse)]
                translation = reference[anchor] - current[cur_pairs[index, 0]] @ rotation
                distances, matches = star_tree.query(current @ rotation + translation)
                good = np.flatnonzero(distances < 2.5)
                if len(good) < 5:
                    continue
                # A reference star may support only one correspondence.
                good = good[np.argsort(distances[good])]
                _, unique = np.unique(matches[good], return_index=True)
                good = good[unique]
                score = len(good)
                error = float(np.median(distances[good]))
                if best is None or (score, -error) > (best[0], -best[1]):
                    best = score, error, good, matches[good]
            if best and best[0] >= max(6, int(min(len(current), len(reference)) * 0.75)):
                break
        if best and best[0] >= max(6, int(min(len(current), len(reference)) * 0.75)):
            break
        if checked >= 1500:
            break
    if best is None or best[0] < max(5, int(min(len(current), len(reference)) * 0.25)):
        raise ValueError("No consistent star alignment found")
    source, destination = current[best[2]], reference[best[3]]
    source_mean, destination_mean = source.mean(axis=0), destination.mean(axis=0)
    u, _, vt = np.linalg.svd((source - source_mean).T @ (destination - destination_mean))
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        raise ValueError("Mirrored field requires a new stack")
    translation = destination_mean - source_mean @ rotation
    residual = float(
        np.sqrt(np.mean(np.sum((source @ rotation + translation - destination) ** 2, axis=1)))
    )
    angle = float(np.degrees(np.arctan2(rotation[0, 1], rotation[0, 0])))
    if abs(angle) > maximum_rotation:
        raise ValueError("Field rotation exceeds the configured alignment limit")
    return rotation, translation, residual, len(source)
