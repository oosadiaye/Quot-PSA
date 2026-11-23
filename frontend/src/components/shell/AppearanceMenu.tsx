import { useEffect, useRef, useState } from 'react';
import { Palette } from 'lucide-react';
import {
  BACKGROUND_PRESETS, DEFAULT_BACKGROUND, applyBackground, loadBackground, normalizeHex, saveBackground,
} from '../../config/appearance';
import '../../styles/appearance.css';

interface AppearanceMenuProps {
  /** Class of the button that opens the panel, so it sits right in the bar it is placed in. */
  buttonClassName?: string;
}

/** A button and a panel to choose the app's background colour: a swatch, any colour, or back to the default. */
export default function AppearanceMenu({ buttonClassName = 'topnav-icon-btn' }: AppearanceMenuProps) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(() => loadBackground());
  const [text, setText] = useState(chosen ?? DEFAULT_BACKGROUND);
  const [error, setError] = useState('');
  const [kept, setKept] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const choose = (hex: string | null) => {
    setChosen(hex);
    setText(hex ?? DEFAULT_BACKGROUND);
    setError('');
    applyBackground(hex);
    setKept(saveBackground(hex));
  };

  const onText = (value: string) => {
    setText(value);
    const hex = normalizeHex(value);
    if (hex) choose(hex);
    else setError('Use a colour like #e8f1ea');
  };

  const current = chosen ?? DEFAULT_BACKGROUND;
  return (
    <div className="appearance" ref={ref}>
      <button
        type="button" className={buttonClassName} aria-label="Background colour" title="Background colour"
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)}
      >
        <Palette size={18} />
      </button>
      {open && (
        <div className="appearance-panel" role="dialog" aria-label="Background colour">
          <h2>Background colour</h2>
          <div className="appearance-swatches">
            {BACKGROUND_PRESETS.map((p) => (
              <button
                key={p.value} type="button" className="appearance-swatch" style={{ background: p.value }}
                aria-label={p.name} title={p.name}
                aria-pressed={current === p.value && (chosen !== null || p.value === DEFAULT_BACKGROUND)}
                onClick={() => choose(p.value === DEFAULT_BACKGROUND ? null : p.value)}
              />
            ))}
          </div>
          <label className="appearance-custom">
            Custom
            <input type="color" aria-label="Pick a colour" value={current} onChange={(e) => choose(e.target.value)} />
            <input type="text" aria-label="Colour code" value={text} onChange={(e) => onText(e.target.value)} spellCheck={false} />
          </label>
          {error && <p className="appearance-error" role="alert">{error}</p>}
          {!kept && <p className="appearance-note">This browser would not save it, so it lasts until you leave.</p>}
          <p className="appearance-note">Applies to the page background in light mode and to the module launcher.</p>
          <button type="button" className="appearance-reset" onClick={() => choose(null)}>Reset to default</button>
        </div>
      )}
    </div>
  );
}
