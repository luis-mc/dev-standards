// scaled(ms): a timing budget for this runner (CIR10 L7). Plain ESM, no dependencies.
// speed_probe.py --export-env sets DELIVERY_SPEED_SCALE once per job. At scale 1 the budget is unchanged.
// A scale above MAX_SCALE, or a bad value, throws: a refusal is an error, never a pass.
// Without the variable the scale is 1 (a developer machine); CI sets it in the job that runs budgets.
export const MAX_SCALE = 3;

export function scaleFromEnv(env = process.env) {
  const raw = env.DELIVERY_SPEED_SCALE;
  if (raw === undefined || raw === "") return 1;
  const v = Number(raw);
  if (!Number.isFinite(v) || v <= 0) throw new Error(`DELIVERY_SPEED_SCALE=${JSON.stringify(raw)} is not a usable scale`);
  if (v > MAX_SCALE) throw new Error(`speed scale ${v} is above ${MAX_SCALE}: this runner is too slow to judge timing budgets`);
  return Math.max(1, v);
}

export function scaled(ms, scale = scaleFromEnv()) {
  return scale === 1 ? ms : Math.ceil(ms * scale);
}
