/**
 * Government Configuration Setup — Quot PSE
 * Route: /settings/government
 *
 * Allows tenant admins to configure:
 * 1. Government Tier (State / LGA)
 * 2. State (from Nigeria's 36 states + FCT)
 * 3. LGA (if tier = LGA)
 *
 * On submit, triggers NCoA seeding for the selected state/tier.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Building2, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import apiClient from '../../api/client';

const GOV_GREEN = '#008751';

interface GovConfig {
    current: {
        government_tier: string;
        state_nbs_code: string;
        state_name: string;
        lga_code: string;
        lga_name: string;
        is_configured: boolean;
    };
    available_states: { code: string; name: string; zone: string }[];
    tiers: { value: string; label: string }[];
}

const ZONE_NAMES: Record<string, string> = {
    '1': 'North-Central', '2': 'North-East', '3': 'North-West',
    '4': 'South-East', '5': 'South-South', '6': 'South-West',
};

export default function GovernmentSetup() {
    const qc = useQueryClient();
    const [tier, setTier] = useState('');
    const [stateCode, setStateCode] = useState('');
    const [lgaCode, setLgaCode] = useState('');
    const [lgaName, setLgaName] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const { data: config, isLoading } = useQuery<GovConfig>({
        queryKey: ['gov-config'],
        queryFn: async () => (await apiClient.get('/tenants/configure-government/')).data,
        staleTime: 60_000,
    });

    // Pre-fill from current config
    useState(() => {
        if (config?.current?.is_configured) {
            setTier(config.current.government_tier);
            setStateCode(config.current.state_nbs_code);
            setLgaCode(config.current.lga_code);
            setLgaName(config.current.lga_name);
        }
    });

    const configureMutation = useMutation({
        mutationFn: async (payload: Record<string, string>) => {
            const { data } = await apiClient.post('/tenants/configure-government/', payload);
            return data;
        },
        onSuccess: (data) => {
            setSuccess(`Government configured: ${data.state_name} (${data.government_tier}). NCoA data seeded.`);
            setError('');
            qc.invalidateQueries({ queryKey: ['gov-config'] });
            qc.invalidateQueries({ queryKey: ['ncoa-segments-all'] });
            qc.invalidateQueries({ queryKey: ['dashboard-stats'] });
        },
        onError: (err: any) => {
            setError(err.response?.data?.error || 'Configuration failed');
            setSuccess('');
        },
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (!tier) { setError('Please select a government tier'); return; }
        if (!stateCode) { setError('Please select a state'); return; }
        if (tier === 'LGA' && !lgaCode) { setError('Please enter the LGA code'); return; }

        configureMutation.mutate({
            government_tier: tier,
            state_nbs_code: stateCode,
            lga_code: lgaCode,
            lga_name: lgaName,
        });
    };

    const selectedState = config?.available_states?.find(s => s.code === stateCode);

    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '12px 14px', borderRadius: '10px',
        border: '1.5px solid #e2e8f0', background: '#fff',
        color: '#1e293b', fontSize: '15px', outline: 'none',
    };
    const selectStyle: React.CSSProperties = { ...inputStyle, appearance: 'auto' as never };
    const labelStyle: React.CSSProperties = {
        display: 'block', marginBottom: '8px', fontSize: '13px',
        fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
    };

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{ maxWidth: '700px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                        <Building2 size={28} style={{ color: GOV_GREEN }} />
                        <h1 style={{ fontSize: '26px', fontWeight: 800, color: '#1e293b', margin: 0 }}>
                            Government Configuration
                        </h1>
                    </div>
                    <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '28px' }}>
                        Configure your government tier and state. This will seed the NCoA Chart of Accounts,
                        MDAs, LGAs, and revenue heads for your selected state.
                    </p>

                    {/* Current status */}
                    {config?.current?.is_configured && (
                        <div style={{
                            padding: '16px 20px', borderRadius: '12px', marginBottom: '24px',
                            background: '#f0fdf4', border: '1.5px solid #bbf7d0',
                            display: 'flex', alignItems: 'center', gap: '10px',
                        }}>
                            <CheckCircle size={20} style={{ color: '#16a34a' }} />
                            <div>
                                <div style={{ fontSize: '14px', fontWeight: 700, color: '#16a34a' }}>
                                    Currently Configured
                                </div>
                                <div style={{ fontSize: '13px', color: '#15803d' }}>
                                    {config.current.state_name} — {config.current.government_tier === 'STATE' ? 'State Government' : `LGA: ${config.current.lga_name || config.current.lga_code}`}
                                </div>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div style={{
                            padding: '14px 18px', borderRadius: '10px', marginBottom: '20px',
                            background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626',
                            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px',
                        }}>
                            <AlertCircle size={18} /> {error}
                        </div>
                    )}

                    {success && (
                        <div style={{
                            padding: '14px 18px', borderRadius: '10px', marginBottom: '20px',
                            background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#16a34a',
                            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px',
                        }}>
                            <CheckCircle size={18} /> {success}
                        </div>
                    )}

                    {isLoading ? (
                        <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>Loading configuration...</div>
                    ) : (
                        <form onSubmit={handleSubmit}>
                            {/* Step 1: Government Tier */}
                            <div style={{
                                background: '#fff', borderRadius: '14px', border: '1px solid #e8ecf1',
                                padding: '28px', marginBottom: '20px',
                            }}>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>
                                    Step 1: Government Tier
                                </div>
                                <label style={labelStyle}>Select your government level *</label>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                                    {[
                                        { value: 'STATE', label: 'State Government', desc: 'Full state-level IFMIS with all ministries and LGAs' },
                                        { value: 'LGA', label: 'Local Government Area', desc: 'LGA-level with departmental structure' },
                                    ].map(opt => (
                                        <div
                                            key={opt.value}
                                            onClick={() => setTier(opt.value)}
                                            style={{
                                                padding: '16px', borderRadius: '10px', cursor: 'pointer',
                                                border: `2px solid ${tier === opt.value ? GOV_GREEN : '#e2e8f0'}`,
                                                background: tier === opt.value ? `${GOV_GREEN}08` : '#fff',
                                                transition: 'all 0.15s',
                                            }}
                                        >
                                            <div style={{ fontSize: '15px', fontWeight: 700, color: tier === opt.value ? GOV_GREEN : '#1e293b' }}>
                                                {opt.label}
                                            </div>
                                            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                                                {opt.desc}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Step 2: State Selection */}
                            <div style={{
                                background: '#fff', borderRadius: '14px', border: '1px solid #e8ecf1',
                                padding: '28px', marginBottom: '20px',
                            }}>
                                <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>
                                    Step 2: Select State
                                </div>
                                <label style={labelStyle}>Nigerian State *</label>
                                <select style={selectStyle} value={stateCode} onChange={e => setStateCode(e.target.value)} required>
                                    <option value="">Select your state...</option>
                                    {Object.entries(
                                        (config?.available_states || []).reduce((groups: Record<string, typeof config.available_states>, state) => {
                                            const zoneName = ZONE_NAMES[state.zone] || `Zone ${state.zone}`;
                                            if (!groups[zoneName]) groups[zoneName] = [];
                                            groups[zoneName].push(state);
                                            return groups;
                                        }, {})
                                    ).map(([zone, states]) => (
                                        <optgroup key={zone} label={zone}>
                                            {states.map(s => (
                                                <option key={s.code} value={s.code}>{s.name} ({s.code})</option>
                                            ))}
                                        </optgroup>
                                    ))}
                                </select>
                                {selectedState && (
                                    <div style={{ marginTop: '8px', fontSize: '13px', color: '#64748b' }}>
                                        Zone: {ZONE_NAMES[selectedState.zone]} | NBS Code: {selectedState.code}
                                    </div>
                                )}
                            </div>

                            {/* Step 3: LGA (only for LGA tier) */}
                            {tier === 'LGA' && (
                                <div style={{
                                    background: '#fff', borderRadius: '14px', border: '1px solid #e8ecf1',
                                    padding: '28px', marginBottom: '20px',
                                }}>
                                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b', marginBottom: '20px' }}>
                                        Step 3: LGA Details
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px' }}>
                                        <div>
                                            <label style={labelStyle}>LGA Code *</label>
                                            <input style={inputStyle} required value={lgaCode}
                                                onChange={e => setLgaCode(e.target.value)}
                                                placeholder="e.g. 08" maxLength={2} />
                                        </div>
                                        <div>
                                            <label style={labelStyle}>LGA Name *</label>
                                            <input style={inputStyle} required value={lgaName}
                                                onChange={e => setLgaName(e.target.value)}
                                                placeholder="e.g. Ilorin West" />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Submit */}
                            <button
                                type="submit"
                                disabled={configureMutation.isPending}
                                style={{
                                    width: '100%', padding: '14px', borderRadius: '10px', border: 'none',
                                    background: GOV_GREEN, color: '#fff', fontSize: '16px', fontWeight: 700,
                                    cursor: 'pointer', display: 'flex', alignItems: 'center',
                                    justifyContent: 'center', gap: '8px',
                                    opacity: configureMutation.isPending ? 0.7 : 1,
                                }}
                            >
                                {configureMutation.isPending ? (
                                    <><Loader2 size={20} className="animate-spin" /> Configuring & Seeding NCoA Data...</>
                                ) : (
                                    <><Building2 size={20} /> Configure Government & Seed NCoA</>
                                )}
                            </button>

                            {configureMutation.isPending && (
                                <div style={{
                                    marginTop: '16px', padding: '14px', borderRadius: '10px',
                                    background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e',
                                    fontSize: '13px', textAlign: 'center',
                                }}>
                                    This may take 10-30 seconds. Seeding NCoA economic codes, geographic data,
                                    MDAs, revenue heads, PAYE brackets, and procurement thresholds...
                                </div>
                            )}
                        </form>
                    )}
                </div>
            </main>
        </div>
    );
}
