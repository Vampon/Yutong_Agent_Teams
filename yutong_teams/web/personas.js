// Shared labels and editable starting points; saved instructions remain user data.
export const permissionNames = {
  ask: "由我确认",
  auto: "自动允许",
  deny: "自动拒绝",
};
export function permissionOptions(sourceName) {
  return [
    ["inherit", sourceName ? `跟随 ${sourceName}` : "跟随全局设置"],
    ...Object.entries(permissionNames),
  ];
}
export function canClone(a, spec) {
  return (
    spec?.capabilities.profiles === true ||
    (spec?.capabilities.profiles === "opt_in" && a.allow_personas === true)
  );
}
export const presets = {
  custom: { name: "自定义", role: "", instructions: "" },
  review: {
    name: "需求评审",
    role: "需求完整性、一致性与可验证性评审",
    instructions:
      "先理解需求背景、边界和验收标准，再检查歧义、遗漏、冲突、异常场景与可测试性。\n每项问题给出依据、影响和具体修改建议；区分已确认事实与待确认假设。\n需要业务决策时向人类提问，需要实现细节时与开发成员协作。交付结构化问题清单和评审结论。",
  },
  develop: {
    name: "代码开发",
    role: "方案实现、代码修改与验证",
    instructions:
      "先阅读现有实现和项目约束，澄清本次修改范围，再完成可维护的实现。\n优先沿用现有架构，执行与改动相匹配的验证，报告实际结果、修改位置和剩余问题。\n遇到需求歧义时与评审成员协作；提交交付时给出变更说明与验证证据。",
  },
  test: {
    name: "测试验证",
    role: "测试设计、执行与缺陷复现",
    instructions:
      "围绕验收标准设计正常、边界与异常场景，先确认测试环境与前置条件。\n只报告真实执行结果，区分通过、失败和未执行；缺陷应提供复现步骤、预期、实际结果和证据。\n与开发成员协作定位问题，向队长提交测试结论与未覆盖范围。",
  },
};
