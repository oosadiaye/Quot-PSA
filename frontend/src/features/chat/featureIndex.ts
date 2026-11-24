import { isNavItemVisible, menuItems, type MenuItem, type ModuleState, type ViewerState } from '../../config/navigation';

/** One screen the user can open, with the menu trail that leads to it. */
export interface Feature {
    path: string;
    name: string;
    /** Menu names from the sidebar down to this screen, e.g. ['Budget & Appropriation', 'Budget Check']. */
    trail: string[];
}

export interface FeatureHit extends Feature {
    score: number;
}

export interface Visibility {
    viewer: ViewerState;
    modules: ModuleState;
}

/** The superadmin console is not part of a tenant user's menu. */
const EXCLUDED_PATHS = new Set(['/superadmin']);

/** Every screen this user may open, read from the same nav tree and visibility rules as the sidebar. */
export function buildFeatureIndex(visibility: Visibility, items: readonly MenuItem[] = menuItems): Feature[] {
    const { viewer, modules } = visibility;
    const seen = new Set<string>();
    const out: Feature[] = [];
    const add = (feature: Feature) => {
        const key = `${feature.path}|${feature.name}`;
        if (EXCLUDED_PATHS.has(feature.path) || seen.has(key)) return;
        seen.add(key);
        out.push(feature);
    };

    for (const item of items) {
        if (!isNavItemVisible(item, viewer, modules)) continue;
        if (!item.subItems?.length) {
            add({ path: item.path, name: item.name, trail: [item.name] });
            continue;
        }
        for (const sub of item.subItems) add({ path: sub.path, name: sub.name, trail: [item.name, sub.name] });
    }
    return out;
}

/** Words that carry no search meaning in "where do I find the ...". */
export const STOPWORDS = new Set([
    'a', 'an', 'the', 'to', 'of', 'in', 'on', 'for', 'and', 'or', 'my', 'me', 'i', 'we', 'is', 'are', 'can', 'do', 'does',
    'how', 'where', 'what', 'which', 'find', 'get', 'go', 'open', 'see', 'show', 'view', 'check', 'look', 'use', 'make',
    'create', 'add', 'new', 'enter', 'record', 'page', 'screen', 'menu', 'with', 'from', 'about', 'want', 'need', 'please',
    'start', 'post', 'raise', 'should', 'would', 'could', 'it', 'this', 'that', 'be',
]);

/** Everyday words and their menu vocabulary. Each side expands to the other. */
const SYNONYM_GROUPS: readonly (readonly string[])[] = [
    ['budget', 'appropriation', 'allocation'],
    ['supplier', 'vendor', 'payable', 'ap', 'creditor'],
    ['bill', 'invoice'],
    ['payment', 'pay', 'disbursement', 'remittance', 'treasury', 'bank', 'cash'],
    ['advance', 'deposit', 'down payment', 'prepayment'],
    ['ledger', 'journal', 'gl', 'accounting'],
    ['buy', 'purchase', 'procurement', 'po'],
    ['requisition', 'request', 'pr'],
    ['grn', 'goods received', 'delivery', 'receiving'],
    ['stock', 'inventory', 'store'],
    ['report', 'statement', 'analysis'],
    ['approve', 'approval', 'workflow'],
    ['user', 'staff', 'employee', 'permission', 'role'],
    ['mda', 'ministry', 'department', 'agency', 'organization'],
    ['salary', 'payroll', 'wage'],
    ['revenue', 'igr', 'income', 'collection'],
    ['contract', 'milestone', 'ipc', 'certificate'],
    ['warrant', 'aie', 'release', 'cash release'],
    ['virement', 'transfer', 'reallocation', 'reallocate'],
];

export const stem = (word: string): string => (word.length > 3 && word.endsWith('s') && !word.endsWith('ss') ? word.slice(0, -1) : word);
export const words = (text: string): string[] => text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean).map(stem);

/** word -> the phrases (as word lists) it can stand for. A multi-word phrase only counts when every word is present. */
const SYNONYMS: ReadonlyMap<string, readonly (readonly string[])[]> = (() => {
    const map = new Map<string, (readonly string[])[]>();
    for (const group of SYNONYM_GROUPS) {
        const phrases = group.map(words);
        phrases.forEach((own, i) => {
            if (own.length !== 1) return;
            map.set(own[0], [...(map.get(own[0]) ?? []), ...phrases.filter((_, j) => j !== i)]);
        });
    }
    return map;
})();

const NAME_WEIGHT = 3;
const TRAIL_WEIGHT = 1.5;
const PATH_WEIGHT = 0.75;
const RELATED_FACTOR = 0.5;
/** Asking for a whole menu by name ('procurement') lists that menu's own screens first. */
const MENU_BONUS = 4;

/** Best matches for a plain-English question, strongest first. Pure and instant, so it works with AI off. */
export function findFeatures(index: readonly Feature[], question: string, limit = 6): FeatureHit[] {
    const tokens = [...new Set(words(question).filter(w => !STOPWORDS.has(w)))];
    if (!tokens.length) return [];

    const hits: FeatureHit[] = [];
    for (const feature of index) {
        const nameWords = words(feature.name);
        const trailWords = words(feature.trail.slice(0, -1).join(' '));
        const pathWords = words(feature.path.replace(/[/-]/g, ' '));
        const weigh = (w: string): number => (nameWords.includes(w) ? NAME_WEIGHT : trailWords.includes(w) ? TRAIL_WEIGHT : pathWords.includes(w) ? PATH_WEIGHT : 0);

        const menuWords = words(feature.trail[0]);
        let score = feature.trail.length > 1 && tokens.every(t => menuWords.includes(t)) ? MENU_BONUS : 0;
        for (const token of tokens) {
            const related = SYNONYMS.get(token) ?? [];
            // A phrase scores the sum of its words, so "down payment" beats a lone "ap".
            const viaSynonym = related.reduce((best, phrase) => {
                const weights = phrase.map(weigh);
                return weights.every(w => w > 0) ? Math.max(best, weights.reduce((x, y) => x + y, 0) * RELATED_FACTOR) : best;
            }, 0);
            score += Math.max(weigh(token), viaSynonym);
        }
        if (score > 0) hits.push({ ...feature, score });
    }
    return hits
        .sort((a, b) => b.score - a.score || a.trail.length - b.trail.length || a.name.localeCompare(b.name))
        .slice(0, limit);
}

/** "Budget & Appropriation > Budget Check" - shown under each result. */
export const trailText = (trail: readonly string[]): string => trail.join(' > ');
