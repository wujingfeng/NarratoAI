export function CreationTypeSelector({ types, selectedType, onChange }) {
  return (
    <section className="create-type-selector" aria-label="选择创作类型">
      <h2>选择创作类型</h2>
      <div className="create-type-selector__list">
        {types.map((type) => (
          <button
            className={`create-type-card${selectedType === type.id ? " is-selected" : ""}`}
            type="button"
            key={type.id}
            data-creation-type={type.id}
            aria-pressed={selectedType === type.id}
            onClick={() => onChange(type.id)}
          >
            <strong>{type.title}</strong>
            <span>{type.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
