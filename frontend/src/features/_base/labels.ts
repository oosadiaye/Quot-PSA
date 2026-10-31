/**
 * "Vehicle Assignments" is the register's name; one record of it is a "Vehicle Assignment". Entities can state their own
 * singular; otherwise it is derived from the label, which is right for ordinary English plurals.
 */
export function singularLabel(label: string, explicit?: string): string {
  if (explicit) return explicit;
  const words = label.trim().split(/\s+/);
  const last = words.pop() ?? '';
  let single = last;
  if (/ies$/i.test(last)) single = last.replace(/ies$/i, 'y');
  else if (/(sses|xes|zes|ches|shes)$/i.test(last)) single = last.slice(0, -2);
  else if (/s$/i.test(last) && !/(ss|us|is)$/i.test(last)) single = last.slice(0, -1);
  return [...words, single].join(' ');
}
