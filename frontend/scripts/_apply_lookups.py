ROOT = r"C:\Users\USER\Documents\Antigravity\public_sector erp"


def edit(rel, pairs):
    p = ROOT + "\\" + rel
    s = open(p, encoding="utf-8-sig", newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    t = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert t.count(a) == 1, (rel, a[:70], t.count(a))
        t = t.replace(a, b)
    open(p, "w", encoding="utf-8", newline="").write(t.replace("\n", nl))


edit("frontend\\src\\features\\_base\\referenceRegistry.ts", [(
    "  'accounting.fundSegment': '/accounting/ncoa/fund/',\n",
    "  'accounting.fundSegment': '/accounting/ncoa/fund/',\n  'accounting.mda': '/accounting/mdas/',\n  'accounting.function': '/accounting/functions/',\n"
    "  'accounting.program': '/accounting/programs/',\n  'accounting.geo': '/accounting/geos/',\n")])

p = ROOT + "\\frontend\\src\\features\\egp\\BidOpeningPanel.tsx"
s = open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
t = s.replace("\r\n", "\n")


def rep(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


rep("import apiClient from '../../api/client';\n", "import apiClient from '../../api/client';\nimport { ReferenceField } from '../_base/ReferenceField';\nimport type { EntityField } from '../_base/types';\n")
rep("interface Dim { id: number; code?: string; name: string }\n", "")
# remove useDim + DimSelect
i = t.index("const useDim = ")
j = t.index("/** Rule on each opened bid")
t = t[:i] + """/** The things an order is charged to. Each is looked up by searching, because a government has hundreds of MDAs and locations. */
const CHARGE_FIELDS: { key: 'mda' | 'fund' | 'function' | 'program' | 'geo' | 'account'; label: string; entity: string }[] = [
  { key: 'mda', label: 'MDA', entity: 'mda' },
  { key: 'fund', label: 'Fund', entity: 'fund' },
  { key: 'function', label: 'Function', entity: 'function' },
  { key: 'program', label: 'Programme', entity: 'program' },
  { key: 'geo', label: 'Location', entity: 'geo' },
  { key: 'account', label: 'Expense account', entity: 'account' },
];
const asField = (c: (typeof CHARGE_FIELDS)[number]): EntityField => ({ name: c.key, label: c.label, type: 'integer', reference: { module: 'accounting', entity: c.entity } });

""" + t[j:]
rep("  const [dims, setDims] = useState({ mda: '', fund: '', function: '', program: '', geo: '', account_code: '' });\n  const mdas = useDim('/accounting/mdas/');\n  const funds = useDim('/accounting/funds/');\n  const functions = useDim('/accounting/functions/');\n  const programs = useDim('/accounting/programs/');\n  const geos = useDim('/accounting/geos/');\n",
    "  const [dims, setDims] = useState<Record<string, number | ''>>({ mda: '', fund: '', function: '', program: '', geo: '', account: '' });\n")
rep("  const set = (k: keyof typeof dims) => (v: string) => setDims((d) => ({ ...d, [k]: v }));\n  const ready = !!pick && Object.values(dims).every((v) => v.trim() !== '');",
    "  const ready = !!pick && Object.values(dims).every((v) => v !== '');")
i = t.index('          <div className="bo-grid">')
j = t.index("          <button type=\"button\" className=\"ef-btn ef-btn-primary\" data-testid=\"bo-award\"")
t = t[:i] + """          <div className="bo-grid">
            {CHARGE_FIELDS.map((c) => (
              <div className="bo-field" key={c.key} data-testid={`bo-${c.key}`}>
                <label htmlFor={`bo-${c.key}-input`}>{c.label}</label>
                <ReferenceField field={asField(c)} id={`bo-${c.key}-input`} value={dims[c.key]} onChange={(v) => setDims((d) => ({ ...d, [c.key]: v }))} />
              </div>
            ))}
          </div>
""" + t[j:]
open(p, "w", encoding="utf-8", newline="").write(t.replace("\n", nl))

edit("egp\\views.py", [(
    """            parts['account'] = Account.objects.filter(code=str(request.data.get('account_code', '')).strip()).first()
            if parts['account'] is None:
                raise awarding.AwardingError('Enter an existing expense account code for the order line.')""",
    """            given = request.data.get('account')
            parts['account'] = (Account.objects.filter(pk=given).first() if given not in (None, '')
                                else Account.objects.filter(code=str(request.data.get('account_code', '')).strip()).first())
            if parts['account'] is None:
                raise awarding.AwardingError('Choose the expense account for the order line.')""")])
edit("egp\\tests\\test_awarding.py", [(
    "        assert r.status_code == 400 and words in r.json()['error'], key",
    "        assert r.status_code == 400 and words in r.json()['error'], key\n\n\ndef test_the_account_may_be_given_by_id_as_the_screen_does():\n    t, (bid,) = opened_tender(['1000'])\n    awarding.assess(bid, 'responsive', None)\n    body = award_body(bid)\n    body['account'] = dims()['account'].pk\n    del body['account_code']\n    r = client_with_role('admin').post(f'/api/v1/egp/tenders/{t.pk}/award/', body, format='json')\n    assert r.status_code == 201, r.json()"),
    ("(('fund', 'fund'), ('mda', 'MDA'), ('account_code', 'expense account'))", "(('fund', 'fund'), ('mda', 'MDA'), ('account_code', 'expense account'))"),
])
print("ok")
