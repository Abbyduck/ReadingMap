import assert from "node:assert/strict";
import { safeNextPath } from "../src/auth/redirect.ts";

const origin = "https://reading-map.example";
const rejected = [null, "", "https://attacker.example", "//attacker.example", "/\\attacker.example", "/\n/attacker.example", "/\r/attacker.example", "/\t/attacker.example", "/ \n/attacker.example", "javascript:alert(1)"];
for (const next of rejected) assert.equal(safeNextPath(next, origin), "/account");
for (const next of ["/", "/admin", "/map?list=2#stage-1", "/bookshelf?search=1"]) {
  assert.equal(safeNextPath(next, origin), next);
  assert.equal(new URL(safeNextPath(next, origin), origin).origin, origin);
}
const decodedAttack = new URLSearchParams("next=/%0a/attacker.example").get("next");
assert.equal(safeNextPath(decodedAttack, origin), "/account");
console.log(`Auth redirect checks passed (${rejected.length + 5} cases).`);
