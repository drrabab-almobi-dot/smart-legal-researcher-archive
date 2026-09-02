import assert from "node:assert/strict";
import test from "node:test";

import {
  legalSearchTerms,
  relevanceScore,
  shouldShowSearchResults,
} from "../lib/arabic-search.ts";

test("results remain empty until a real query is submitted", () => {
  assert.equal(shouldShowSearchResults(""), false);
  assert.equal(shouldShowSearchResults("   ـــ  "), false);
  assert.equal(shouldShowSearchResults("ترويج المخدرات"), true);
});

test("a multi-word legal query requires and rewards its direct context", () => {
  const direct = relevanceScore({
    title: "مخدرات - ترويج الحشيش المخدر",
    subject: "ترويج المخدرات",
    fullText: "إدانة المتهم بترويج مادة مخدرة",
  }, "ترويج المخدرات");
  const unrelated = relevanceScore({
    title: "جوائز شراء",
    subject: "جوائز التجار للمشترين",
    fullText: "جوائز حصل عليها المشترون لترويج البضائع",
  }, "ترويج المخدرات");

  assert.ok(direct.score > unrelated.score);
  assert.ok(direct.matchedTerms.includes("ترويج"));
  assert.ok(direct.matchedTerms.includes("المخدرات"));
});

test("synonym expansion is bounded and keeps the original legal token", () => {
  const terms = legalSearchTerms("تعويض الضرر");
  assert.ok(terms.expanded.includes("تعويض"));
  assert.ok(terms.expanded.length <= 16);
});
