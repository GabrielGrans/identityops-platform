import { useId, useState } from "react";

export type DirectoryOption = { id: number; name: string; searchText?: string };

function matches(option: DirectoryOption, term: string) {
  return `${option.name} ${option.searchText ?? ""}`.toLowerCase().includes(term.trim().toLowerCase());
}

export function SearchSelect({ label, name, options, initial = "", optional = false }: {
  label: string; name: string; options: DirectoryOption[]; initial?: string; optional?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [value, setValue] = useState(initial);
  const visible = options.filter(option => String(option.id) === value || matches(option, term));
  return <div className="directory-picker">
    <label>Search {label.toLowerCase()}<input type="search" value={term} onChange={event => setTerm(event.target.value)} /></label>
    <label>{label}<select name={name} required={!optional} value={options.some(option => String(option.id) === value) ? value : ""} onChange={event => setValue(event.target.value)}>
      <option value="">{optional ? "None" : "Select an option"}</option>
      {visible.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}
    </select></label>
    {!visible.length && <p>No matching options.</p>}
  </div>;
}

export function SearchChecks({ label, options, selected, onChange }: {
  label: string; options: DirectoryOption[]; selected: number[]; onChange: (ids: number[]) => void;
}) {
  const [term, setTerm] = useState("");
  const visible = options.filter(option => matches(option, term));
  return <fieldset className="directory-picker">
    <legend>{label} ({selected.length} selected)</legend>
    <label>Search {label.toLowerCase()}<input type="search" value={term} onChange={event => setTerm(event.target.value)} /></label>
    <div className="directory-options">
      {visible.map(option => <label key={option.id} className="iam-checkbox">
        <input type="checkbox" checked={selected.includes(option.id)}
          disabled={selected.length >= 100 && !selected.includes(option.id)}
          onChange={event => onChange(event.target.checked
            ? [...selected, option.id] : selected.filter(id => id !== option.id))} /> {option.name}
      </label>)}
      {!visible.length && <p>No matching options.</p>}
    </div>
  </fieldset>;
}

export function DirectoryPagination({ page, total, onPage }: {
  page: number; total: number; onPage: (page: number) => void;
}) {
  const labelId = useId();
  return <div className="iam-actions" role="group" aria-labelledby={labelId}>
    <button className="secondary-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
    <span id={labelId}>Page {page} of {total}</span>
    <button className="secondary-button" disabled={page >= total} onClick={() => onPage(page + 1)}>Next</button>
  </div>;
}
