/**
 * Storage Module
 * Handles persistence of custom exchange pairs using localStorage.
 */

const STORAGE_KEY = 'weeth_custom_pairs_v1';

export function getSavedPairs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error('Failed to load pairs', e);
    return [];
  }
}

export function savePair(pair) {
  const pairs = getSavedPairs();
  // Check if exists by ID or Address combo
  const existingIdx = pairs.findIndex(p => p.id === pair.id);
  
  if (existingIdx >= 0) {
    pairs[existingIdx] = pair;
  } else {
    pairs.push(pair);
  }
  
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pairs));
  return pairs;
}

export function deletePair(id) {
  const pairs = getSavedPairs();
  const next = pairs.filter(p => p.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}
