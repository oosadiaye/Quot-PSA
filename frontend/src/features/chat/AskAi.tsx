import { useMemo, useState } from 'react';
import { ArrowRight, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { findFeatures, trailText, type Feature } from './featureIndex';
import { findGuides } from './knowledge/findGuides';
import type { Guide } from './knowledge/guides';
import { useFeatureIndex } from './useAskAi';

interface Props {
    /** Called after the user follows a result, so the chat panel can get out of the way. */
    onNavigate: () => void;
}

const EXAMPLES = ['How do I post a budget', 'Check budget', 'Pay a supplier', 'Add a user', 'Trial balance'];
const MIN_QUERY = 2;

function GuideCard({ guide, feature, onOpen }: { guide: Guide; feature?: Feature; onOpen: (path: string) => void }) {
    return (
        <li className="ai-result" data-testid="ai-guide" data-guide={guide.id}>
            <div className="ai-result-head">
                <span className="ai-result-name">{guide.title}</span>
                {feature && <span className="ai-trail">{trailText(feature.trail)}</span>}
            </div>
            <ol className="ai-steps" data-testid="ai-steps">
                {guide.steps.map(step => <li key={step}>{step}</li>)}
            </ol>
            {guide.screen && (
                <button type="button" className="ai-open" data-testid="ai-open" onClick={() => onOpen(guide.screen!)}>
                    Take me there <ArrowRight size={14} aria-hidden="true" />
                </button>
            )}
        </li>
    );
}

function ScreenCard({ feature, onOpen }: { feature: Feature; onOpen: (path: string) => void }) {
    return (
        <li className="ai-result" data-testid="ai-result" data-path={feature.path}>
            <div className="ai-result-head">
                <span className="ai-result-name">{feature.name}</span>
                <span className="ai-trail">{trailText(feature.trail)}</span>
            </div>
            <button type="button" className="ai-open" data-testid="ai-open" onClick={() => onOpen(feature.path)}>
                Take me there <ArrowRight size={14} aria-hidden="true" />
            </button>
        </li>
    );
}

/**
 * "How do I...?" and "where is...?" for the whole system. Answers come from the menu and a set of
 * written guides, never from your data, and only ever name screens this user can open.
 */
export default function AskAi({ onNavigate }: Props) {
    const navigate = useNavigate();
    const index = useFeatureIndex();
    const [query, setQuery] = useState('');
    const ready = query.trim().length >= MIN_QUERY;

    const guides = useMemo(() => (ready ? findGuides(index, query) : []), [index, query, ready]);
    const screens = useMemo(() => {
        if (!ready) return [];
        const guided = new Set(guides.map(g => g.screen));
        return findFeatures(index, query).filter(f => !guided.has(f.path));
    }, [index, query, ready, guides]);
    const byPath = useMemo(() => new Map(index.map(f => [f.path, f])), [index]);

    const open = (path: string) => {
        navigate(path);
        onNavigate();
    };

    return (
        <div className="ai-body" data-testid="ai-panel">
            <div className="chat-search ai-search">
                <Search size={15} aria-hidden="true" />
                <input
                    type="search" value={query} data-testid="ai-input" data-enter-skip
                    placeholder="e.g. how do I post a budget" aria-label="Ask how to do something or where to find it"
                    onChange={e => setQuery(e.target.value)}
                />
            </div>

            <div className="ai-results" aria-live="polite">
                {(guides.length > 0 || screens.length > 0) && (
                    <ul className="ai-list">
                        {guides.map(g => <GuideCard key={g.id} guide={g} feature={g.screen ? byPath.get(g.screen) : undefined} onOpen={open} />)}
                        {screens.map(f => <ScreenCard key={`${f.path}|${f.name}`} feature={f} onOpen={open} />)}
                    </ul>
                )}

                {ready && guides.length === 0 && screens.length === 0 && (
                    <div className="chat-empty" data-testid="ai-none">Nothing in your menu matches that. Try other words.</div>
                )}

                {!ready && (
                    <div className="ai-intro">
                        <p>Ask how to do something or where it is: posting a budget, checking a budget, paying a supplier. You get the steps and a link.</p>
                        <div className="ai-chips">
                            {EXAMPLES.map(example => (
                                <button key={example} type="button" className="ai-chip" onClick={() => setQuery(example)}>{example}</button>
                            ))}
                        </div>
                        <p className="ai-note">Answers come from the menu and the user guide. They never read or quote your figures.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
