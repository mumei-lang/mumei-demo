export function len(name?: string): number {
  return name!.length; // Bug: non-null assertion on nullable parameter
}
