import { stem, type Feature } from '../featureIndex';
import { GUIDES, type Guide } from './guides';

/**
 * Words that mean the same thing in a question, folded to one form. Unlike the screen search these
 * verbs matter here: "post a budget" (do it) and "check a budget" (look at it) are different guides.
 */
const FOLDS: readonly (readonly string[])[] = [
    ['create', 'post', 'enter', 'raise', 'make', 'add', 'new', 'prepare', 'record', 'capture', 'upload', 'load', 'register'],
    ['check', 'view', 'see', 'review', 'verify', 'show', 'lookup', 'status', 'balance', 'available', 'left', 'remaining'],
    ['budget', 'appropriation'],
    ['supplier', 'vendor'],
    ['invoice', 'bill'],
    ['pay', 'disburse', 'settle'],
];
const FOLD = new Map(FOLDS.flatMap(group => group.map(w => [w, group[0]] as const)));

const FILLER = new Set(['a', 'an', 'the', 'to', 'of', 'in', 'on', 'for', 'and', 'or', 'my', 'me', 'i', 'we', 'how', 'do', 'does', 'can', 'where', 'what', 'should', 'would', 'could', 'please', 'want', 'need', 'is', 'are', 'it', 'this', 'that', 'be', 'some']);

const fold = (text: string): string[] =>
    text.toLowerCase().split(/[^a-z0-9]+/).filter(w => w && !FILLER.has(w)).map(w => {
        const base = stem(w);
        return FOLD.get(w) ?? FOLD.get(base) ?? base;
    });

/** The guide's strongest phrase that is wholly present in the question, as the number of words it needs. */
function matchStrength(guide: Guide, question: ReadonlySet<string>): number {
    let best = 0;
    for (const ask of guide.asks) {
        const phrase = fold(ask);
        if (phrase.length > best && phrase.every(w => question.has(w))) best = phrase.length;
    }
    return best;
}

/**
 * Guides that answer the question, best first. A guide is offered only when the screen it starts on
 * is in the user's own feature index, so nobody is told to open a menu they cannot see.
 */
export function findGuides(index: readonly Feature[], question: string, limit = 3, guides: readonly Guide[] = GUIDES): Guide[] {
    const asked = new Set(fold(question));
    if (!asked.size) return [];
    const reachable = new Set(index.map(f => f.path));
    return guides
        .filter(g => g.screen === null || reachable.has(g.screen))
        .map(guide => ({ guide, strength: matchStrength(guide, asked) }))
        .filter(m => m.strength > 0)
        .sort((a, b) => b.strength - a.strength)
        .slice(0, limit)
        .map(m => m.guide);
}
