/**
 * Warrant Printout Settings — tenant-wide configuration for the
 * AIE/Warrant printout. One row per tenant; auto-created on first
 * GET via the singleton endpoint
 *   /budget/warrant-printout-settings/current/.
 *
 * Three signature slots: Executive Governor, Honourable Commissioner
 * for Finance, Accountant-General — uploaded as PNG/JPG. Replacing
 * any signature is a high-trust operation; the backend gates writes
 * to staff/superuser only.
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    FileSignature, Upload, Image as ImageIcon,
    CheckCircle, AlertTriangle, Eye, X,
} from 'lucide-react';

import apiClient from '../../api/client';
import SettingsLayout from './SettingsLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import PdfPreviewModal from '../../components/PdfPreviewModal';

// ─────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────
interface WarrantPrintoutSettings {
    id: number;
    state_name: string;
    ministry_of_finance_name: string;
    office_address: string;
    letterhead_logo_url: string | null;
    governor_name: string;
    governor_title: string;
    governor_signature_url: string | null;
    finance_commissioner_name: string;
    finance_commissioner_title: string;
    finance_commissioner_signature_url: string | null;
    accountant_general_name: string;
    accountant_general_title: string;
    accountant_general_signature_url: string | null;
    footer_notes: string;
    reference_pdf_template_url: string | null;
}

// ─────────────────────────────────────────────────────────────────────
// Hooks
// ─────────────────────────────────────────────────────────────────────
const ENDPOINT = '/budget/warrant-printout-settings/current/';

const useWarrantSettings = () =>
    useQuery<WarrantPrintoutSettings>({
        queryKey: ['warrant-printout-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get(ENDPOINT);
            return data;
        },
    });

const useUpdateWarrantSettings = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (form: FormData) => {
            const { data } = await apiClient.patch(ENDPOINT, form, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data as WarrantPrintoutSettings;
        },
        // Push the server response straight into the cache so the page
        // updates the moment the PATCH completes — no waiting for a
        // background refetch to swap the old image URL for the new one.
        // Then invalidate to keep the cache reconciled with anything
        // else that might have changed server-side.
        onSuccess: (fresh) => {
            qc.setQueryData(['warrant-printout-settings'], fresh);
            qc.invalidateQueries({
                queryKey: ['warrant-printout-settings'],
                refetchType: 'none',
            });
        },
    });
};

// ─────────────────────────────────────────────────────────────────────
// Letterhead logo — image-only, uploaded as the warrant-specific
// coat-of-arms / crest. Mirrors the signature slot UX so the page
// reads as one cohesive "image attachment" pattern.
// ─────────────────────────────────────────────────────────────────────
interface LetterheadLogoUploaderProps {
    imageUrl: string | null;
    pendingFile: File | null;
    onFileChange: (field: string, file: File | null) => void;
}

function LetterheadLogoUploader({
    imageUrl, pendingFile, onFileChange,
}: LetterheadLogoUploaderProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const previewUrl = pendingFile
        ? URL.createObjectURL(pendingFile)
        : imageUrl ?? null;
    useEffect(() => {
        return () => {
            if (pendingFile && previewUrl) URL.revokeObjectURL(previewUrl);
        };
    }, [pendingFile, previewUrl]);

    return (
        <div>
            <div style={{ ...fieldLabel, marginBottom: 6 }}>Letterhead Logo</div>
            <div style={{
                border: '2px dashed #cbd5e1', borderRadius: 8,
                height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#f8fafc', position: 'relative', overflow: 'hidden',
            }}>
                {previewUrl ? (
                    <img
                        src={previewUrl}
                        alt="Letterhead logo"
                        style={{
                            maxWidth: '100%', maxHeight: '100%',
                            objectFit: 'contain', padding: 6,
                        }}
                    />
                ) : (
                    <div style={{
                        color: '#94a3b8', fontSize: 12, display: 'flex',
                        alignItems: 'center', gap: 6,
                    }}>
                        <ImageIcon size={14} /> No logo uploaded
                    </div>
                )}
            </div>
            <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                ref={inputRef}
                style={{ display: 'none' }}
                onChange={e => onFileChange('letterhead_logo', e.target.files?.[0] ?? null)}
            />
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    style={smallBtn}
                >
                    <Upload size={12} /> {previewUrl ? 'Replace' : 'Upload'}
                </button>
                {pendingFile && (
                    <button
                        type="button"
                        onClick={() => onFileChange('letterhead_logo', null)}
                        style={{ ...smallBtn, background: '#fff', color: '#dc2626' }}
                    >
                        <X size={12} /> Cancel pick
                    </button>
                )}
            </div>
            <div style={{
                marginTop: 6, fontSize: 10, color: '#94a3b8',
                lineHeight: 1.4,
            }}>
                State coat of arms / crest. Falls back to Branding logo if empty.
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────
// Reusable signature-slot card
// ─────────────────────────────────────────────────────────────────────
interface SignatureSlotProps {
    label: string;
    name: string;
    nameField: string;
    titleField: string;
    title: string;
    imageUrl: string | null;
    imageField: string;
    onTextChange: (field: string, value: string) => void;
    onFileChange: (field: string, file: File | null) => void;
    pendingFile: File | null;
}

function SignatureSlot({
    label, name, nameField, title, titleField,
    imageUrl, imageField, onTextChange, onFileChange, pendingFile,
}: SignatureSlotProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    // Show a preview from the pending file if the user just picked one,
    // otherwise the persisted URL from the server.
    const previewUrl = pendingFile
        ? URL.createObjectURL(pendingFile)
        : imageUrl ?? null;
    useEffect(() => {
        // Revoke the object URL when the component unmounts / file changes
        // so we don't leak blob references.
        return () => {
            if (pendingFile && previewUrl) URL.revokeObjectURL(previewUrl);
        };
    }, [pendingFile, previewUrl]);

    return (
        <div style={{
            border: '1px solid #e2e8f0', borderRadius: 10,
            padding: 20, background: '#fff',
            display: 'grid', gridTemplateColumns: '1fr 240px', gap: 24,
            alignItems: 'start',
        }}>
            <div>
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontSize: 12, fontWeight: 700, color: '#1e40af',
                    textTransform: 'uppercase', letterSpacing: 0.6,
                    marginBottom: 12,
                }}>
                    <FileSignature size={14} /> {label}
                </div>
                <div style={{ display: 'grid', gap: 12 }}>
                    <div>
                        <label style={fieldLabel}>Full Name</label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => onTextChange(nameField, e.target.value)}
                            placeholder="e.g. Sheriff Oborevwori"
                            style={textInput}
                        />
                    </div>
                    <div>
                        <label style={fieldLabel}>Title (printed under signature)</label>
                        <input
                            type="text"
                            value={title}
                            onChange={e => onTextChange(titleField, e.target.value)}
                            style={textInput}
                        />
                    </div>
                </div>
            </div>

            <div>
                <div style={{ ...fieldLabel, marginBottom: 6 }}>Signature image</div>
                <div style={{
                    border: '2px dashed #cbd5e1', borderRadius: 8,
                    height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: '#f8fafc', position: 'relative', overflow: 'hidden',
                }}>
                    {previewUrl ? (
                        <img
                            src={previewUrl}
                            alt={`${label} signature`}
                            style={{
                                maxWidth: '100%', maxHeight: '100%',
                                objectFit: 'contain', padding: 6,
                            }}
                        />
                    ) : (
                        <div style={{
                            color: '#94a3b8', fontSize: 12, display: 'flex',
                            alignItems: 'center', gap: 6,
                        }}>
                            <ImageIcon size={14} /> No signature uploaded
                        </div>
                    )}
                </div>
                <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    ref={inputRef}
                    style={{ display: 'none' }}
                    onChange={e => onFileChange(imageField, e.target.files?.[0] ?? null)}
                />
                <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                    <button
                        type="button"
                        onClick={() => inputRef.current?.click()}
                        style={smallBtn}
                    >
                        <Upload size={12} /> {previewUrl ? 'Replace' : 'Upload'}
                    </button>
                    {previewUrl && pendingFile && (
                        <button
                            type="button"
                            onClick={() => onFileChange(imageField, null)}
                            style={{ ...smallBtn, background: '#fff', color: '#dc2626' }}
                        >
                            Cancel pick
                        </button>
                    )}
                </div>
                <div style={{
                    marginTop: 6, fontSize: 10, color: '#94a3b8',
                    lineHeight: 1.4,
                }}>
                    PNG with transparent background recommended.
                    Replaces any existing signature on save.
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────
export default function WarrantPrintoutSettingsPage() {
    const { data, isLoading } = useWarrantSettings();
    const updateMutation = useUpdateWarrantSettings();

    const [text, setText] = useState<Partial<WarrantPrintoutSettings>>({});
    const [files, setFiles] = useState<{
        letterhead_logo: File | null;
        governor_signature: File | null;
        finance_commissioner_signature: File | null;
        accountant_general_signature: File | null;
        reference_pdf_template: File | null;
    }>({
        letterhead_logo: null,
        governor_signature: null,
        finance_commissioner_signature: null,
        accountant_general_signature: null,
        reference_pdf_template: null,
    });
    const [savedAt, setSavedAt] = useState<Date | null>(null);
    const [error, setError] = useState<string | null>(null);
    // Toggle for the in-app PDF preview modal — replaces the
    // previous behaviour where clicking "View current sample" would
    // navigate the user out of the app to a raw backend media URL.
    const [previewOpen, setPreviewOpen] = useState(false);

    // ⚠️ All hooks (useState/useEffect/useRef) MUST sit above the
    // ``if (isLoading || !data) return <LoadingScreen />`` early-return
    // below. React tracks hooks by call order, and an early return that
    // skips a later hook trips "Rendered more hooks than during the
    // previous render". ``referencePdfRef`` lives here for that reason.
    const referencePdfRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (data) setText(data);
    }, [data]);

    if (isLoading || !data) return <LoadingScreen />;

    const handleTextChange = (field: string, value: string) => {
        setText(prev => ({ ...prev, [field]: value }));
        setSavedAt(null);
    };
    const handleFileChange = (field: string, file: File | null) => {
        setFiles(prev => ({ ...prev, [field]: file }));
        setSavedAt(null);
    };

    const handleSave = async () => {
        setError(null);
        const form = new FormData();
        // Text fields — only ones the user actually edits show in the
        // form. We send the lot for atomic patches.
        const textFields: Array<keyof WarrantPrintoutSettings> = [
            'state_name', 'ministry_of_finance_name', 'office_address',
            'governor_name', 'governor_title',
            'finance_commissioner_name', 'finance_commissioner_title',
            'accountant_general_name', 'accountant_general_title',
            'footer_notes',
        ];
        for (const f of textFields) {
            const v = (text as Record<string, unknown>)[f];
            if (typeof v === 'string') form.append(f, v);
        }
        // File fields — only append when the user picked a new file.
        for (const [k, file] of Object.entries(files)) {
            if (file) form.append(k, file);
        }
        try {
            await updateMutation.mutateAsync(form);
            setSavedAt(new Date());
            // Clear pending files after successful save.
            setFiles({
                letterhead_logo: null,
                governor_signature: null,
                finance_commissioner_signature: null,
                accountant_general_signature: null,
                reference_pdf_template: null,
            });
        } catch (e: unknown) {
            const errObj = e as { response?: { data?: unknown }; message?: string };
            setError(
                typeof errObj?.response?.data === 'string'
                    ? errObj.response.data
                    : JSON.stringify(errObj?.response?.data ?? errObj?.message ?? 'Save failed'),
            );
        }
    };

    const t = text as WarrantPrintoutSettings;

    return (
        <SettingsLayout
            title="Warrant Printout Settings"
            breadcrumb="Settings"
            subtitle="Letterhead, signatures, and reference template used when printing AIE / Warrant documents"
            icon={<FileSignature size={20} color="white" />}
            gradient="linear-gradient(135deg, #1e40af, #312e81)"
            gradientShadow="rgba(30, 64, 175, 0.25)"
            maxWidth="1080px"
        >
            <div style={{ display: 'grid', gap: 18 }}>
                {/* Save banner */}
                {savedAt && (
                    <div style={{
                        padding: '10px 14px', borderRadius: 8,
                        background: '#ecfdf5', border: '1px solid #a7f3d0',
                        color: '#047857', fontSize: 13,
                        display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                        <CheckCircle size={16} /> Saved at {savedAt.toLocaleTimeString()}
                    </div>
                )}
                {error && (
                    <div style={{
                        padding: '10px 14px', borderRadius: 8,
                        background: '#fef2f2', border: '1px solid #fecaca',
                        color: '#b91c1c', fontSize: 13,
                        display: 'flex', alignItems: 'flex-start', gap: 8,
                    }}>
                        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                        <div>{error}</div>
                    </div>
                )}

                {/* Letterhead section */}
                <section style={card}>
                    <h3 style={cardTitle}>Letterhead</h3>
                    <p style={cardHint}>
                        State + ministry identity printed at the top of every warrant.
                        The letterhead logo (state coat of arms) is composed onto every
                        warrant printout above the title; falls back to the global
                        Branding logo when not configured here.
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 240px', gap: 24, alignItems: 'start' }}>
                        <div style={{ display: 'grid', gap: 12 }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                <div>
                                    <label style={fieldLabel}>State Name</label>
                                    <input type="text" value={t.state_name ?? ''}
                                        onChange={e => handleTextChange('state_name', e.target.value)}
                                        style={textInput} />
                                </div>
                                <div>
                                    <label style={fieldLabel}>Ministry of Finance</label>
                                    <input type="text" value={t.ministry_of_finance_name ?? ''}
                                        onChange={e => handleTextChange('ministry_of_finance_name', e.target.value)}
                                        style={textInput} />
                                </div>
                            </div>
                            <div>
                                <label style={fieldLabel}>Office Address</label>
                                <textarea value={t.office_address ?? ''}
                                    onChange={e => handleTextChange('office_address', e.target.value)}
                                    rows={2}
                                    style={{ ...textInput, resize: 'vertical', minHeight: 60 }}
                                />
                            </div>
                        </div>

                        {/* Letterhead logo uploader — same UX shape as the
                            signature slots so the page reads as one consistent
                            "image attachment" pattern. */}
                        <LetterheadLogoUploader
                            imageUrl={t.letterhead_logo_url}
                            pendingFile={files.letterhead_logo}
                            onFileChange={handleFileChange}
                        />
                    </div>
                </section>

                {/* Three signature slots */}
                <section style={card}>
                    <h3 style={cardTitle}>Signatories</h3>
                    <p style={cardHint}>
                        These three signatures are composed onto every warrant printout.
                        Only platform admins can upload — uploading the Accountant-General's
                        signature is a high-trust operation. Replacement preserves no audit
                        history of the prior file.
                    </p>
                    <div style={{ display: 'grid', gap: 14 }}>
                        <SignatureSlot
                            label="Executive Governor of Delta State"
                            name={t.governor_name ?? ''}
                            nameField="governor_name"
                            title={t.governor_title ?? ''}
                            titleField="governor_title"
                            imageUrl={t.governor_signature_url}
                            imageField="governor_signature"
                            onTextChange={handleTextChange}
                            onFileChange={handleFileChange}
                            pendingFile={files.governor_signature}
                        />
                        <SignatureSlot
                            label="Honourable Commissioner for Finance"
                            name={t.finance_commissioner_name ?? ''}
                            nameField="finance_commissioner_name"
                            title={t.finance_commissioner_title ?? ''}
                            titleField="finance_commissioner_title"
                            imageUrl={t.finance_commissioner_signature_url}
                            imageField="finance_commissioner_signature"
                            onTextChange={handleTextChange}
                            onFileChange={handleFileChange}
                            pendingFile={files.finance_commissioner_signature}
                        />
                        <SignatureSlot
                            label="Accountant-General of Delta State"
                            name={t.accountant_general_name ?? ''}
                            nameField="accountant_general_name"
                            title={t.accountant_general_title ?? ''}
                            titleField="accountant_general_title"
                            imageUrl={t.accountant_general_signature_url}
                            imageField="accountant_general_signature"
                            onTextChange={handleTextChange}
                            onFileChange={handleFileChange}
                            pendingFile={files.accountant_general_signature}
                        />
                    </div>
                </section>

                {/* Footer + reference PDF */}
                <section style={card}>
                    <h3 style={cardTitle}>Footer &amp; reference template</h3>
                    <div style={{ display: 'grid', gap: 14 }}>
                        <div>
                            <label style={fieldLabel}>Footer notes</label>
                            <textarea value={t.footer_notes ?? ''}
                                onChange={e => handleTextChange('footer_notes', e.target.value)}
                                rows={2} placeholder="e.g. Distribution: AGF · CBN · Internal Audit"
                                style={{ ...textInput, resize: 'vertical', minHeight: 60 }} />
                        </div>
                        <div>
                            <label style={fieldLabel}>Reference PDF template</label>
                            <p style={{ ...cardHint, marginTop: 0, marginBottom: 8 }}>
                                The agreed sample warrant document. Stored as a design
                                reference so the printout layout can be audited against it;
                                never injected into actual printouts (each warrant has unique
                                data).
                            </p>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                                {t.reference_pdf_template_url ? (
                                    <button
                                        type="button"
                                        onClick={() => setPreviewOpen(true)}
                                        style={{
                                            display: 'inline-flex', alignItems: 'center', gap: 6,
                                            padding: '6px 12px', borderRadius: 6,
                                            border: '1px solid #cbd5e1', background: '#fff',
                                            color: '#1e40af', fontSize: 13, fontWeight: 600,
                                            cursor: 'pointer',
                                        }}
                                    >
                                        <Eye size={14} /> View current sample
                                    </button>
                                ) : (
                                    <span style={{ color: '#94a3b8', fontSize: 13 }}>
                                        No sample uploaded yet
                                    </span>
                                )}
                                <input
                                    ref={referencePdfRef}
                                    type="file"
                                    accept="application/pdf"
                                    style={{ display: 'none' }}
                                    onChange={e =>
                                        handleFileChange(
                                            'reference_pdf_template',
                                            e.target.files?.[0] ?? null,
                                        )
                                    }
                                />
                                <button
                                    type="button"
                                    onClick={() => referencePdfRef.current?.click()}
                                    style={smallBtn}
                                >
                                    <Upload size={12} />
                                    {files.reference_pdf_template
                                        ? `Picked: ${files.reference_pdf_template.name}`
                                        : 'Upload new sample'}
                                </button>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Save bar */}
                <div style={{
                    display: 'flex', justifyContent: 'flex-end',
                    paddingTop: 4,
                }}>
                    <button
                        type="button"
                        onClick={handleSave}
                        disabled={updateMutation.isPending}
                        style={{
                            padding: '10px 22px', borderRadius: 8,
                            border: 'none',
                            background: updateMutation.isPending
                                ? '#94a3b8'
                                : 'linear-gradient(135deg, #1e40af, #312e81)',
                            color: '#fff', fontWeight: 700, fontSize: 14,
                            cursor: updateMutation.isPending ? 'progress' : 'pointer',
                            boxShadow: '0 4px 12px rgba(30, 64, 175, 0.25)',
                        }}
                    >
                        {updateMutation.isPending ? 'Saving…' : 'Save changes'}
                    </button>
                </div>
            </div>

            {/* In-app PDF preview — replaces the previous behaviour
                where clicking "View current sample" took the user out
                of the app to a raw backend media URL. The modal
                renders the PDF via the browser's native PDF viewer
                (iframe) so we don't need to bundle PDF.js. */}
            {previewOpen && (
                <PdfPreviewModal
                    url={t.reference_pdf_template_url}
                    title="Warrant Sample Template"
                    subtitle={`${t.state_name || 'State'} · agreed reference layout`}
                    onClose={() => setPreviewOpen(false)}
                />
            )}
        </SettingsLayout>
    );
}

// ─────────────────────────────────────────────────────────────────────
// Inline styles
// ─────────────────────────────────────────────────────────────────────
const card: React.CSSProperties = {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 12,
    padding: 22,
};
const cardTitle: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 700,
    margin: 0,
    color: '#0f172a',
};
const cardHint: React.CSSProperties = {
    margin: '4px 0 14px 0',
    color: '#64748b',
    fontSize: 13,
    lineHeight: 1.5,
};
const fieldLabel: React.CSSProperties = {
    display: 'block',
    fontSize: 11,
    fontWeight: 700,
    color: '#475569',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 6,
};
const textInput: React.CSSProperties = {
    width: '100%',
    padding: '8px 11px',
    borderRadius: 6,
    border: '1px solid #cbd5e1',
    fontSize: 14,
    fontFamily: 'inherit',
    color: '#0f172a',
    background: '#fff',
    outline: 'none',
};
const smallBtn: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '6px 10px',
    fontSize: 11,
    fontWeight: 600,
    color: '#1e40af',
    background: '#fff',
    border: '1px solid #cbd5e1',
    borderRadius: 6,
    cursor: 'pointer',
};
