/**
 * Shared types for the data-driven CRUD registry pages powering the 15
 * future modules. Each module ships a `config.ts` that describes its
 * entities declaratively; the generic list/form components render from it.
 */

export type FieldType =
  | 'text'
  | 'longtext'
  | 'number'
  | 'decimal'
  | 'integer'
  | 'date'
  | 'datetime'
  | 'boolean'
  | 'select'
  | 'object';

export interface EntityField {
  /** JSON key sent to / received from the API. */
  name: string;
  label: string;
  type: FieldType;
  /** For `select`: allowed values keyed by stored value → human label. */
  options?: Record<string, string>;
  /** FK: `{ module, entity }` → render a numeric FK id in an input. */
  reference?: { module: string; entity: string };
  required?: boolean;
  placeholder?: string;
  readOnly?: boolean;
  /** When true (default for decimal), right-align in the table. */
  numeric?: boolean;
  /** Hide from the create/edit form (server-managed fields). */
  hideInForm?: boolean;
  /** Auxiliary columns displayed only in the expanded card on mobile. */
  secondary?: boolean;
}

export interface EntityConfig {
  /** Camel-case key used in the URL path, e.g. 'staffAdvance'. */
  key: string;
  /** Plural path segment on the backend, e.g. 'staff-advances'. */
  plural: string;
  label: string;
  /** Field used for the search query param. */
  searchField: string;
  /** Columns shown in the table (subset of fields). */
  columns: EntityField[];
  /** All fields available to the create/edit form. */
  fields: EntityField[];
  /** Optional status field name → rendered with StatusBadge. */
  statusField?: string;
  /** PK field name. Defaults to 'id'. */
  idField?: string;
  /** Optional hard-coded filter params appended to the list query. */
  fixedParams?: Record<string, any>;
}

export interface ModuleConfig {
  key: string;
  label: string;
  icon: string;
  description: string;
  basePath: string;
  entities: EntityConfig[];
}
