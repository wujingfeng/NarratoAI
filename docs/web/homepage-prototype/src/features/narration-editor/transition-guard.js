/**
 * Synchronous guard for async save/switch/generate transitions.
 * React state alone is not sufficient because two click handlers can run before
 * the disabled state is committed.
 */
export function createTransitionGuard(onChange = () => {}) {
  let active = "";

  return {
    get active() {
      return active;
    },
    get busy() {
      return Boolean(active);
    },
    begin(name) {
      if (active || typeof name !== "string" || !name) return false;
      active = name;
      onChange(active);
      return true;
    },
    end(name) {
      if (!active || active !== name) return false;
      active = "";
      onChange(active);
      return true;
    },
  };
}
