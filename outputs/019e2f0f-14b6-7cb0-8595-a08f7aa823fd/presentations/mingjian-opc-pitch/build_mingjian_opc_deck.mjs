import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";

import {
  ensureArtifactToolWorkspace,
  importArtifactTool,
  saveBlobToFile,
} from "/Users/kral/.codex/plugins/cache/openai-primary-runtime/presentations/26.515.10909/skills/presentations/scripts/artifact_tool_utils.mjs";

const WORKSPACE = "/Users/kral/project/agents/outputs/019e2f0f-14b6-7cb0-8595-a08f7aa823fd/presentations/mingjian-opc-pitch";
const OUTPUT_DIR = "/Users/kral/project/agents";
const FINAL_PPTX = path.join(OUTPUT_DIR, "明鉴_OPC路演优化版.pptx");
const FINAL_PPTX_V2 = path.join(OUTPUT_DIR, "明鉴_OPC路演优化版_新版.pptx");
const FINAL_PPTX_PRICE = path.join(OUTPUT_DIR, "明鉴_OPC路演优化版_价格重做版.pptx");
const PREVIEW_DIR = path.join(WORKSPACE, "preview-new");
const CONTACT_SHEET = path.join(PREVIEW_DIR, "contact-sheet.png");
const SKILL_DIR = "/Users/kral/.codex/plugins/cache/openai-primary-runtime/presentations/26.515.10909/skills/presentations";
const PYTHON = "/Users/kral/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";

const W = 1280;
const H = 720;

const C = {
  bg: "#F7FAFC",
  ink: "#0F172A",
  muted: "#64748B",
  line: "#D9E2EC",
  navy: "#111827",
  navy2: "#172033",
  teal: "#14B8A6",
  tealDark: "#0F766E",
  blue: "#2563EB",
  indigo: "#4F46E5",
  purple: "#7C3AED",
  amber: "#F59E0B",
  red: "#EF4444",
  green: "#10B981",
  white: "#FFFFFF",
  paleTeal: "#DDF7F1",
  paleBlue: "#EAF2FF",
  paleAmber: "#FFF4D6",
  paleRed: "#FFE8E8",
  palePurple: "#F1EAFE",
};

const FONT = "PingFang SC";

function addBg(slide, dark = false) {
  slide.background.fill = { type: "solid", color: dark ? C.navy : C.bg };
  const bg = slide.shapes.add({
    geometry: "rect",
    position: { left: 0, top: 0, width: W, height: H },
    fill: { type: "solid", color: dark ? C.navy : C.bg },
    line: { fill: { type: "none" }, width: 0 },
  });
  bg.sendToBack();
}

function shape(slide, x, y, w, h, fill = C.white, line = C.line, geometry = "roundRect") {
  return slide.shapes.add({
    geometry,
    position: { left: x, top: y, width: w, height: h },
    fill: typeof fill === "string" ? { type: "solid", color: fill } : fill,
    line: line === "none" ? { fill: { type: "none" }, width: 0 } : { fill: line, width: 1.2 },
  });
}

function text(slide, body, x, y, w, h, opts = {}) {
  const t = slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill: { type: "none" },
    line: { fill: { type: "none" }, width: 0 },
  });
  t.text.style = {
    fontSize: opts.size ?? 20,
    typeface: opts.font ?? FONT,
    color: opts.color ?? C.ink,
    bold: opts.bold ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    lineSpacing: opts.lineSpacing ?? 1.12,
  };
  t.text = body;
  return t;
}

function bar(slide, title, markerColor, page, dark = false) {
  const fill = dark ? C.navy : C.navy2;
  shape(slide, 0, 0, W, 66, fill, "none", "rect");
  shape(slide, 52, 24, 6, 22, markerColor, "none", "rect");
  text(slide, title, 72, 18, 820, 34, { size: 24, bold: true, color: C.white, valign: "middle" });
  text(slide, String(page).padStart(2, "0"), 1188, 21, 40, 24, { size: 14, bold: true, color: "#91A4BD", align: "right" });
}

function footer(slide, dark = false) {
  text(slide, "MingJian · OPC 单人 + AI 创业项目路演", 52, 678, 520, 18, {
    size: 12,
    color: dark ? "#94A3B8" : "#7A899A",
  });
}

function chip(slide, label, x, y, fill, color = C.ink, w = 118) {
  const c = shape(slide, x, y, w, 30, fill, "none", "roundRect");
  c.text.style = { fontSize: 13, typeface: FONT, color, bold: true, alignment: "center", verticalAlignment: "middle" };
  c.text = label;
  return c;
}

function metric(slide, value, label, x, y, w, color, sub = "") {
  shape(slide, x, y, w, 116, C.white, "#DCE5EF");
  text(slide, value, x + 20, y + 18, w - 40, 42, { size: 38, bold: true, color });
  text(slide, label, x + 20, y + 62, w - 40, 24, { size: 16, bold: true, color: C.ink });
  if (sub) text(slide, sub, x + 20, y + 88, w - 40, 18, { size: 12, color: C.muted });
}

function card(slide, title, body, x, y, w, h, accent = C.teal, fill = C.white) {
  shape(slide, x, y, w, h, fill, "#DCE5EF");
  shape(slide, x, y, 7, h, accent, "none", "rect");
  text(slide, title, x + 22, y + 18, w - 38, 25, { size: 18, bold: true, color: accent });
  text(slide, body, x + 22, y + 52, w - 38, h - 64, { size: 14, color: C.ink, lineSpacing: 1.2 });
}

function bulletList(slide, items, x, y, w, opts = {}) {
  const body = items.map((v) => `• ${v}`).join("\n");
  return text(slide, body, x, y, w, opts.h ?? 150, {
    size: opts.size ?? 15,
    color: opts.color ?? C.ink,
    lineSpacing: opts.lineSpacing ?? 1.25,
  });
}

function connector(slide, x1, y1, x2, y2, color = C.line, width = 2) {
  const dx = Math.abs(x2 - x1);
  const dy = Math.abs(y2 - y1);
  if (dx >= dy) {
    return shape(slide, Math.min(x1, x2), (y1 + y2) / 2 - width / 2, dx, width, color, "none", "rect");
  }
  return shape(slide, (x1 + x2) / 2 - width / 2, Math.min(y1, y2), width, dy, color, "none", "rect");
}

function slide01(presentation) {
  const slide = presentation.slides.add();
  addBg(slide, true);
  shape(slide, 600, 46, 642, 404, { type: "solid", color: "#07101F" }, "#24334A");
  shape(slide, 630, 76, 582, 344, "#0B1220", "#25364F");
  shape(slide, 650, 100, 92, 296, "#101C2F", "none");
  ["分析", "辩论", "证据", "监控"].forEach((v, i) => {
    shape(slide, 666, 132 + i * 48, 58, 24, i === 1 ? "#123E46" : "#17283F", "none");
    text(slide, v, 676, 136 + i * 48, 38, 12, { size: 10, bold: true, color: i === 1 ? "#A7F3D0" : "#B8C7D8", align: "center" });
  });
  shape(slide, 760, 102, 410, 54, "#14243A", "#263A56");
  text(slide, "AI 决策工作台", 782, 120, 160, 18, { size: 16, bold: true, color: C.white });
  text(slide, "Evidence · Debate · Trace", 980, 122, 160, 14, { size: 11, color: "#94A3B8", align: "right" });
  [[760, 184, 126, 78, C.paleTeal, "证据链"], [904, 184, 126, 78, C.paleBlue, "辩论"], [1048, 184, 122, 78, C.paleAmber, "仲裁"]].forEach(([x, y, w, h, fill, label]) => {
    shape(slide, x, y, w, h, fill, "none");
    text(slide, label, x + 16, y + 18, w - 32, 18, { size: 14, bold: true, color: C.ink, align: "center" });
    shape(slide, x + 22, y + 50, w - 44, 6, "#CBD5E1", "none", "rect");
  });
  shape(slide, 760, 292, 410, 72, "#111D2F", "#263A56");
  [0.28, 0.62, 0.44, 0.78].forEach((v, i) => {
    shape(slide, 790 + i * 82, 334 - v * 42, 42, v * 42, [C.teal, C.blue, C.amber, C.purple][i], "none", "rect");
  });
  text(slide, "实时证据流", 782, 306, 120, 16, { size: 12, bold: true, color: "#A7F3D0" });
  text(slide, "明鉴 MingJian", 64, 92, 520, 68, { size: 52, bold: true, color: C.white });
  text(slide, "证据驱动的多智能体决策平台", 68, 174, 520, 34, { size: 25, color: "#A7F3D0", bold: true });
  text(slide, "把 AI 分析从“生成答案”升级为“可验证、可追溯、可复现的决策流程”。", 68, 235, 478, 86, {
    size: 22,
    color: "#D8E2EF",
    lineSpacing: 1.22,
  });
  chip(slide, "OPC 单人 + AI", 68, 344, "#132A3D", "#A7F3D0", 142);
  chip(slide, "开源获客", 224, 344, "#132A3D", "#A7F3D0", 118);
  chip(slide, "商业部署", 356, 344, "#132A3D", "#A7F3D0", 118);
  metric(slide, "10+", "实时数据源", 68, 488, 178, C.teal, "新闻/社区/代码/RSS");
  metric(slide, "9", "智能体委员会", 270, 488, 178, C.blue, "支持/质疑/仲裁");
  metric(slide, "19", "GitHub Stars", 472, 488, 178, C.amber, "截至 2026-05-16");
  metric(slide, "3条", "变现路径", 674, 488, 178, C.purple, "订阅/部署/服务");
  text(slide, "演讲：曹涵哲", 946, 608, 240, 26, { size: 18, color: "#CBD5E1", align: "right" });
  footer(slide, true);
  return slide;
}

function slide02(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "项目简述：不是聊天机器人，而是 AI 决策参谋团", C.teal, 2);
  text(slide, "一句话", 72, 112, 140, 22, { size: 16, bold: true, color: C.tealDark });
  text(slide, "明鉴接入实时数据源，让多个 AI 智能体基于证据进行支持、质疑和仲裁，最终生成可审计的分析报告。", 72, 142, 760, 82, {
    size: 32,
    bold: true,
    color: C.ink,
    lineSpacing: 1.15,
  });
  card(slide, "服务对象", "投研人员、企业战略部门、咨询顾问、风险监控团队。", 72, 288, 260, 122, C.blue, C.paleBlue);
  card(slide, "核心交付", "证据链、辩论记录、仲裁结论、决策回溯和可导出报告。", 360, 288, 260, 122, C.teal, C.paleTeal);
  card(slide, "商业形态", "开源核心框架推广，Cloud 团队基础使用转化，企业定制服务盈利。", 648, 288, 260, 122, C.purple, C.palePurple);
  shape(slide, 950, 116, 232, 388, C.navy, "none");
  text(slide, "用户输入问题", 982, 150, 168, 28, { size: 18, bold: true, color: C.white, align: "center" });
  ["证据采集", "多 Agent 辩论", "仲裁裁决", "报告与回溯"].forEach((v, i) => {
    const y = 202 + i * 66;
    shape(slide, 982, y, 168, 42, i % 2 ? "#1E293B" : "#123E46", "none");
    text(slide, v, 998, y + 9, 136, 18, { size: 15, bold: true, color: i % 2 ? "#E2E8F0" : "#A7F3D0", align: "center" });
  });
  text(slide, "最终输出：可验证决策建议", 976, 470, 180, 24, { size: 16, bold: true, color: "#FDE68A", align: "center" });
  footer(slide);
  return slide;
}

function slide03(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "真痛点：AI 分析看起来很快，但严肃决策不敢直接信", C.red, 3);
  const pains = [
    ["幻觉当事实", "模型可能编造数据、来源和结论，用户难以辨别真假。"],
    ["单模型盲区", "一个模型一种视角，没有反方质疑，偏见很难暴露。"],
    ["黑盒不可审计", "只有答案，没有证据链、推理链和责任链。"],
    ["工作流碎片化", "搜索、分析、辩论、报告分散在多个工具里，上下文不断丢失。"],
  ];
  pains.forEach(([a, b], i) => {
    const x = 70 + (i % 2) * 550;
    const y = 128 + Math.floor(i / 2) * 170;
    card(slide, a, b, x, y, 500, 132, C.red, C.paleRed);
  });
  shape(slide, 70, 502, 1088, 76, C.navy, "none");
  text(slide, "投资人关心的不是“AI 会不会回答”，而是它能不能降低决策风险、形成可复用流程并被客户持续付费。", 98, 522, 1032, 30, {
    size: 24,
    bold: true,
    color: C.white,
    align: "center",
    valign: "middle",
  });
  footer(slide);
  return slide;
}

function slide04(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "解决方案：证据链 + 对抗辩论 + 仲裁回溯", C.teal, 4);
  const steps = [
    ["1", "实时数据", "Google News / GitHub / Reddit / GDELT / RSS"],
    ["2", "证据提取", "提炼事实、来源、置信度和争议点"],
    ["3", "智能体辩论", "支持方、挑战方、多视角专家交叉质询"],
    ["4", "仲裁裁决", "加权整合证据，形成明确建议"],
    ["5", "报告回溯", "导出报告，保留来源与决策记录"],
  ];
  steps.forEach(([n, title, desc], i) => {
    const x = 70 + i * 235;
    shape(slide, x, 158, 190, 160, i % 2 ? C.paleBlue : C.paleTeal, "#C7D7E8");
    shape(slide, x + 18, 178, 38, 38, i % 2 ? C.blue : C.teal, "none", "ellipse");
    text(slide, n, x + 18, 184, 38, 18, { size: 18, bold: true, color: C.white, align: "center" });
    text(slide, title, x + 22, 234, 150, 28, { size: 20, bold: true, color: C.ink });
    text(slide, desc, x + 22, 268, 146, 40, { size: 12.5, color: C.muted, lineSpacing: 1.18 });
    if (i < steps.length - 1) connector(slide, x + 190, 238, x + 235, 238, "#9EB2C7", 2);
  });
  card(slide, "用户获得什么", "不是一句“看似正确”的结论，而是一套完整证据包：引用来源、反方质疑、仲裁理由、后续行动建议。", 92, 400, 500, 120, C.teal, C.white);
  card(slide, "为什么可商业化", "越高风险、越多人参与、越需要留痕的决策场景，越愿意为可靠流程、私有部署和持续监控付费。", 650, 400, 500, 120, C.amber, C.paleAmber);
  footer(slide);
  return slide;
}

function slide05(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "产品已经可用：有界面、有 API、有部署路径", C.blue, 5);
  shape(slide, 600, 118, 580, 355, C.navy, "#23324A");
  shape(slide, 626, 146, 528, 292, "#0B1220", "#2B3C58");
  shape(slide, 646, 170, 84, 244, "#111D2F", "none");
  ["总览", "助手", "辩论", "证据", "设置"].forEach((v, i) => {
    shape(slide, 658, 194 + i * 38, 60, 20, i === 2 ? "#123E46" : "#17283F", "none");
    text(slide, v, 666, 198 + i * 38, 44, 10, { size: 9, bold: true, color: i === 2 ? "#A7F3D0" : "#B8C7D8", align: "center" });
  });
  shape(slide, 758, 174, 366, 46, "#14243A", "#263A56");
  text(slide, "多智能体辩论任务", 780, 188, 160, 18, { size: 15, bold: true, color: C.white });
  [["支持方", C.teal], ["挑战方", C.red], ["仲裁官", C.amber]].forEach(([v, color], i) => {
    shape(slide, 760 + i * 122, 248, 104, 66, "#111D2F", "#263A56");
    shape(slide, 778 + i * 122, 264, 16, 16, color, "none", "ellipse");
    text(slide, v, 804 + i * 122, 262, 46, 16, { size: 12, bold: true, color: C.white });
    shape(slide, 780 + i * 122, 292, 62, 5, "#334155", "none", "rect");
  });
  shape(slide, 760, 344, 366, 62, "#111D2F", "#263A56");
  shape(slide, 786, 374, 58, 8, C.teal, "none", "rect");
  shape(slide, 856, 360, 58, 22, C.blue, "none", "rect");
  shape(slide, 926, 366, 58, 16, C.amber, "none", "rect");
  shape(slide, 996, 352, 58, 30, C.purple, "none", "rect");
  text(slide, "证据强度 / 争议程度 / 决策建议", 780, 358, 280, 12, { size: 10, color: "#94A3B8" });
  text(slide, "核心模块", 72, 122, 420, 34, { size: 32, bold: true, color: C.ink });
  bulletList(slide, [
    "多智能体辩论：支持、质疑、仲裁形成决策委员会",
    "证据库：来源、声明、信号、趋势结构化沉淀",
    "工作台：把分析、推演、报告放在一个流程里",
    "Docker 部署：支持本地运行和未来私有化交付",
    "开源协议清晰，利于企业试用和生态扩散",
  ], 76, 178, 455, { h: 230, size: 17, lineSpacing: 1.38 });
  metric(slide, "FastAPI", "后端 API", 76, 470, 190, C.teal);
  metric(slide, "Next.js", "前端工作台", 290, 470, 190, C.blue);
  metric(slide, "Vector", "知识与证据", 504, 470, 190, C.purple);
  footer(slide);
  return slide;
}

function slide06(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "创新性与核心壁垒：不是堆模型，而是决策流程工程", C.purple, 6);
  const items = [
    ["多智能体对抗", "用支持方和挑战方互相纠偏，避免单模型盲区。", C.blue, C.paleBlue],
    ["证据链追踪", "每个结论绑定来源、论点和推理过程，便于审计。", C.teal, C.paleTeal],
    ["确定性回溯", "保存辩论、仲裁、决策记录，支持复盘与问责。", C.amber, C.paleAmber],
    ["自修复引擎", "Jarvis 审查输出质量，失败时重规划和迭代。", C.red, C.paleRed],
    ["多模型路由", "不同角色可接入不同模型，兼顾能力与成本。", C.purple, C.palePurple],
    ["自部署能力", "支持数据留在本地，为企业私有部署打开空间。", C.green, "#E7F8EF"],
  ];
  items.forEach(([t, b, accent, fill], i) => {
    const x = 70 + (i % 3) * 382;
    const y = 126 + Math.floor(i / 3) * 190;
    card(slide, t, b, x, y, 330, 132, accent, fill);
  });
  text(slide, "壁垒随时间增强：行业模板、证据结构、客户私有连接器、部署经验会不断沉淀。", 104, 558, 980, 28, {
    size: 22,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide07(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "目标市场：先切高价值研究与风险决策场景", C.amber, 7);
  const segments = [
    ["投资研究", "行业趋势、公司风险、投资论点辩论", "愿为速度和可靠性付费"],
    ["竞品/战略", "竞品动态、市场机会、进入策略", "企业部门可团队采购"],
    ["风险监控", "舆情、政策、供应链、突发事件", "适合持续监控订阅"],
    ["咨询/政策", "多利益方评估、报告生成、客户交付", "适合私有部署和定制"],
  ];
  segments.forEach(([t, b, k], i) => {
    const x = 78 + i * 288;
    shape(slide, x, 150, 248, 250, C.white, "#DAE5F0");
    shape(slide, x, 150, 248, 10, [C.blue, C.teal, C.amber, C.purple][i], "none", "rect");
    text(slide, t, x + 22, 188, 200, 28, { size: 22, bold: true, color: C.ink });
    text(slide, b, x + 22, 232, 192, 62, { size: 15, color: C.muted, lineSpacing: 1.22 });
    text(slide, k, x + 22, 326, 192, 42, { size: 15, bold: true, color: [C.blue, C.tealDark, C.amber, C.purple][i], lineSpacing: 1.15 });
  });
  shape(slide, 108, 472, 1040, 82, C.navy, "none");
  text(slide, "首个落地切口：投研 + 竞品分析 + 风险监控。它们共同特点是信息变化快、错误代价高、报告交付频繁。", 140, 494, 976, 34, {
    size: 24,
    bold: true,
    color: C.white,
    align: "center",
    valign: "middle",
  });
  footer(slide);
  return slide;
}

function slide08(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "市场反应：已开源发布，进入真实社区验证", C.green, 8);
  text(slide, "公开验证指标", 72, 116, 400, 34, { size: 30, bold: true });
  metric(slide, "19", "GitHub Stars", 78, 176, 230, C.amber, "截至 2026-05-16");
  metric(slide, "2026.03", "项目创建", 334, 176, 230, C.blue, "GitHub 公开仓库");
  metric(slide, "开源", "协议清晰", 590, 176, 230, C.teal, "企业友好");
  metric(slide, "可运行", "产品原型", 846, 176, 230, C.purple, "前端 + API + Docker");
  card(slide, "已有反馈", "中文 AI 社区对“多 Agent 辩论 + 证据链”的方向有讨论；开发者关注点集中在部署、模型接入、数据源和应用场景。", 78, 344, 500, 126, C.green, "#E8F8EF");
  card(slide, "下一步验证", "用 GitHub Star、Issue、Demo 访问、等待名单和 3 家试点客户，验证真实需求和付费意愿。", 626, 344, 500, 126, C.blue, C.paleBlue);
  text(slide, "市场反应页的原则：只讲可验证事实，不虚构收入和客户；把“关注”转化为试点、等待名单和付费验证。", 110, 540, 1000, 26, {
    size: 20,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide09(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "盈利计划：三层商业结构，先推广再转化再盈利", C.teal, 9);
  const xs = [112, 466, 820];
  const stages = [
    ["开源核心框架", "¥0", "用于推广\n建立信任与社区"],
    ["团队基础使用", "¥299/席/月起", "对应 Cloud 版本\n团队协作与持续使用"],
    ["企业定制服务", "¥30万-100万+/项目", "盈利方向\n私有部署与行业交付"],
  ];
  stages.forEach(([t, price, b], i) => {
    shape(slide, xs[i], 160, 290, 148, i === 0 ? C.paleTeal : C.white, "#D3E0EC");
    text(slide, t, xs[i] + 24, 180, 242, 24, { size: 21, bold: true, color: [C.tealDark, C.blue, C.amber][i], align: "center" });
    text(slide, price, xs[i] + 24, 212, 242, 30, { size: i === 2 ? 22 : 24, bold: true, color: C.ink, align: "center" });
    text(slide, b, xs[i] + 30, 252, 230, 42, { size: 15, color: C.ink, align: "center", lineSpacing: 1.18 });
    if (i < 2) connector(slide, xs[i] + 290, 234, xs[i + 1], 234, "#94A3B8", 2);
  });
  card(slide, "收入来源", "Cloud 团队版按席位订阅；企业定制按项目收费，标准项目 ¥30万-100万+，后续收取年度维护和升级服务费。", 92, 382, 480, 122, C.teal, C.paleTeal);
  card(slide, "获客策略", "GitHub 开源核心框架积累信任，V2EX/掘金/B站/Reddit 做 Demo 传播，再把活跃用户导向 Cloud 试点和企业交付。", 628, 382, 480, 122, C.blue, C.paleBlue);
  text(slide, "核心逻辑：开源核心框架负责传播，Cloud 承接团队基础使用，企业定制服务贡献主要收入。", 126, 562, 960, 28, {
    size: 22,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide10(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "版本与价格：一个公共核心，两条商业化产品线", C.purple, 10);
  text(slide, "投资人要看清楚三件事：免费版负责获客，Cloud 形成订阅收入，企业定制版贡献高客单和长期服务费。", 92, 96, 1096, 26, {
    size: 18,
    bold: true,
    color: C.ink,
    align: "center",
  });
  const plans = [
    ["agents", "公共核心", "¥0", "永久免费开源", "上游主线", ["公共核心框架", "用于推广与建立信任", "沉淀通用 Agent 能力", "所有商业版本从这里复用"]],
    ["mingjian-cloud", "团队基础使用", "¥299/席/月起", "SaaS 订阅收费", "Cloud 版本", ["多租户账号和团队空间", "云端任务、报告和额度", "持续运维、监控和更新", "形成可预测订阅收入"]],
    ["mingjian-enterprise", "商业定制版", "¥30万-100万+", "POC ¥5-10万；年服务费 15%-20%", "企业部署", ["SSO / 权限 / 审计", "企业数据连接器", "高可用 HA 和内网部署", "项目交付 + 长期服务"]],
  ];
  plans.forEach(([name, role, price, billing, target, features], i) => {
    const x = 82 + i * 390;
    const dark = i === 2;
    shape(slide, x, 132, 320, 402, dark ? C.navy : C.white, dark ? C.navy : "#DCE5EF");
    text(slide, name, x + 28, 156, 264, 28, { size: 23, bold: true, color: dark ? C.white : [C.tealDark, C.blue, C.amber][i], align: "center" });
    text(slide, role, x + 28, 192, 264, 26, { size: 21, bold: true, color: dark ? "#CBD5E1" : C.ink, align: "center" });
    shape(slide, x + 30, 230, 260, 58, dark ? "#172033" : "#F8FBFF", dark ? "#334155" : "#DCE5EF");
    text(slide, "价格", x + 48, 238, 224, 14, { size: 12, bold: true, color: dark ? "#CBD5E1" : C.muted, align: "center" });
    text(slide, price, x + 42, 250, 236, 24, { size: i === 2 ? 22 : 24, bold: true, color: dark ? "#FDE68A" : C.ink, align: "center" });
    text(slide, billing, x + 42, 274, 236, 12, { size: i === 2 ? 10 : 11, bold: true, color: dark ? "#A7F3D0" : [C.tealDark, C.blue, C.amber][i], align: "center" });
    text(slide, target, x + 28, 306, 264, 22, { size: 15, bold: true, color: dark ? "#CBD5E1" : C.muted, align: "center" });
    bulletList(slide, features, x + 46, 346, 238, { h: 100, size: 13, color: dark ? "#E2E8F0" : C.ink, lineSpacing: 1.24 });
    if (i === 0) chip(slide, "推广入口", x + 96, 474, "#DDF7F1", C.tealDark, 128);
    if (i === 1) chip(slide, "订阅收入", x + 96, 474, "#DBEAFE", C.blue, 128);
    if (i === 2) chip(slide, "盈利主线", x + 96, 474, "#FEF3C7", "#92400E", 128);
  });
  text(slide, "商业定制版定价逻辑：先用 ¥5-10万 POC 降低成交门槛，再按部署复杂度、连接器数量、HA/审计要求报价 ¥30万-100万+。", 100, 570, 1080, 32, {
    size: 20,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide11(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "需求投入与财务测算：轻资产启动，靠订阅和部署回本", C.amber, 11);
  text(slide, "早期主要投入", 72, 112, 400, 28, { size: 28, bold: true });
  const rows = [
    ["Token / API 调用", "多模型辩论、证据分析、报告生成", "¥500-2,000/月"],
    ["模型会员", "OpenAI / Claude / Gemini / Grok 测试接入", "¥500-1,500/月"],
    ["公司服务器", "API、数据库、任务队列、模型网关", "¥800-3,000/月"],
    ["网站服务器", "官网、文档、Demo、等待名单", "¥100-500/月"],
    ["开发设备", "本地开发、演示、模型实验", "¥10,000-20,000 一次性"],
    ["宣传成本", "视频、物料、社区推广、参赛展示", "¥1,000-5,000/阶段"],
  ];
  rows.forEach((r, i) => {
    const y = 158 + i * 54;
    shape(slide, 72, y, 640, 42, i % 2 ? "#F8FBFF" : C.white, "#E1E9F2", "rect");
    text(slide, r[0], 92, y + 10, 150, 18, { size: 14, bold: true });
    text(slide, r[1], 260, y + 10, 290, 18, { size: 13, color: C.muted });
    text(slide, r[2], 570, y + 10, 126, 18, { size: 13, bold: true, color: C.amber, align: "right" });
  });
  shape(slide, 760, 158, 380, 332, C.navy, "none");
  text(slide, "回本样例", 792, 190, 300, 30, { size: 28, bold: true, color: C.white });
  text(slide, "Cloud 团队版：¥299 / 席 / 月", 792, 244, 300, 24, { size: 20, bold: true, color: "#FDE68A" });
  text(slide, "10 个团队客户 × 每队 5 席", 792, 290, 300, 24, { size: 18, color: "#CBD5E1" });
  text(slide, "= ¥14,950 / 月", 792, 330, 300, 46, { size: 36, bold: true, color: "#A7F3D0" });
  text(slide, "若月运营成本控制在 ¥3,000-8,000，早期可通过 Cloud 团队版 + 企业定制服务实现正现金流。", 792, 404, 300, 62, {
    size: 15,
    color: "#E2E8F0",
    lineSpacing: 1.22,
  });
  text(slide, "注：以上为路演测算模型，真实金额可随 API 用量、服务器规格和推广节奏调整。", 86, 568, 1020, 20, { size: 13, color: C.muted });
  footer(slide);
  return slide;
}

function slide12(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "公司架构：一人主力驱动 + Hermes 多智能体协作", C.blue, 12);
  text(slide, "组织形态不是传统团队堆人，而是创始人负责判断和交付，Hermes Agent 通过 Telegram 连接 5 个 Bot 分工执行。", 78, 96, 1120, 30, {
    size: 18,
    bold: true,
    color: C.ink,
    align: "center",
  });

  shape(slide, 70, 150, 370, 346, C.navy, "none");
  text(slide, "Telegram Bot 协作层", 100, 178, 250, 24, { size: 22, bold: true, color: C.white });
  text(slide, "Hermes agent 已接入的 5 个执行入口", 100, 210, 250, 18, { size: 13, color: "#94A3B8" });
  const bots = [
    ["PR 助理", "Reddit / 社区推广策略"],
    ["全能编码助理", "代码实现、测试、修复"],
    ["宣传部", "内容发布、增长运营"],
    ["明鉴项目组", "项目管理、任务推进"],
    ["秘书处", "会议、提醒、资料整理"],
  ];
  bots.forEach(([name, desc], i) => {
    const y = 246 + i * 47;
    shape(slide, 100, y, 40, 40, i === 0 ? C.teal : "#1E293B", "none", "ellipse");
    text(slide, String(i + 1), 114, y + 10, 12, 16, { size: 13, bold: true, color: i === 0 ? "#063C36" : "#CBD5E1", align: "center" });
    text(slide, name, 156, y + 2, 180, 20, { size: 17, bold: true, color: C.white });
    text(slide, desc, 156, y + 24, 210, 14, { size: 11, color: "#94A3B8" });
    shape(slide, 384, y + 18, 22, 4, [C.teal, C.blue, C.amber, C.green, C.purple][i], "none", "rect");
  });

  connector(slide, 440, 322, 510, 322, "#9FB2C7", 2);
  shape(slide, 510, 196, 260, 252, C.white, "#CAD6E3");
  shape(slide, 548, 226, 184, 64, C.navy, "none");
  text(slide, "曹涵哲", 578, 242, 126, 28, { size: 28, bold: true, color: C.white, align: "center" });
  text(slide, "创始人 / 总调度", 544, 304, 190, 18, { size: 14, bold: true, color: C.blue, align: "center" });
  bulletList(slide, [
    "确定产品方向与商业判断",
    "设计 AI 架构和关键流程",
    "审核 Bot 产出并最终交付",
  ], 542, 340, 196, { h: 76, size: 13, lineSpacing: 1.25 });

  connector(slide, 770, 322, 840, 322, "#9FB2C7", 2);
  shape(slide, 840, 150, 370, 346, C.white, "#DCE5EF");
  text(slide, "形成可复制的 OPC 工作流", 872, 178, 280, 24, { size: 22, bold: true, color: C.ink });
  const flows = [
    ["任务分发", "需求、Bug、推广、路演任务进入 Telegram"],
    ["Agent 执行", "5 个 Bot 按角色输出代码、文案、计划和资料"],
    ["人工仲裁", "创始人筛选、校验、合并和发布"],
    ["沉淀资产", "代码、文档、模板和宣传经验持续复用"],
  ];
  flows.forEach(([name, desc], i) => {
    const y = 224 + i * 58;
    shape(slide, 872, y, 42, 42, [C.blue, C.teal, C.amber, C.purple][i], "none", "ellipse");
    text(slide, String(i + 1), 887, y + 10, 12, 16, { size: 14, bold: true, color: C.white, align: "center" });
    text(slide, name, 932, y, 190, 20, { size: 16, bold: true, color: C.ink });
    text(slide, desc, 932, y + 24, 230, 16, { size: 11, color: C.muted });
  });

  shape(slide, 198, 548, 884, 54, C.paleTeal, "#BCEADD");
  text(slide, "核心表达：明鉴的公司架构本身就是产品方法论的证明，一个人主导关键判断，多智能体承担执行与增长。", 224, 562, 832, 20, {
    size: 17,
    bold: true,
    color: C.tealDark,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide13(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "阶段规划：用三步把开源关注转为商业收入", C.green, 13);
  const phases = [
    ["0-3个月", "产品验证", ["优化 README 和 Demo", "完成 V2EX/掘金/B站/Reddit 推广", "建立等待名单", "争取 3 家试点访谈"]],
    ["3-6个月", "付费试点", ["推出 Cloud 等待名单", "打磨投研/竞品/风险模板", "完成 1-2 个企业定制 POC", "形成第一批付费用户"]],
    ["6-12个月", "商业复制", ["Cloud 团队基础使用", "企业连接器", "行业模板包", "标准化部署和支持体系"]],
  ];
  phases.forEach(([time, title, items], i) => {
    const x = 82 + i * 380;
    shape(slide, x, 146, 320, 354, C.white, "#DCE5EF");
    shape(slide, x, 146, 320, 12, [C.teal, C.blue, C.purple][i], "none", "rect");
    text(slide, time, x + 26, 186, 250, 34, { size: 30, bold: true, color: [C.tealDark, C.blue, C.purple][i] });
    text(slide, title, x + 26, 232, 250, 28, { size: 22, bold: true, color: C.ink });
    bulletList(slide, items, x + 30, 290, 250, { h: 150, size: 15, lineSpacing: 1.35 });
  });
  text(slide, "每个阶段都要有可量化指标：Star / Demo 访问 / 等待名单 / 试点客户 / 付费转化。", 142, 560, 940, 26, {
    size: 22,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide14(presentation) {
  const slide = presentation.slides.add();
  addBg(slide);
  bar(slide, "风险管控：提前回答评委和投资人的追问", C.red, 14);
  const risks = [
    ["模型成本波动", "缓存、模型路由、任务额度、用户自带 Key，控制单位成本。"],
    ["市场冷启动", "开源社区获客，先做高价值窄场景，再复制到企业客户。"],
    ["数据合规风险", "默认引用公开来源；企业定制服务支持私有部署、权限和审计。"],
    ["产品过重", "开源核心框架保持轻量，Cloud 与企业定制承载商业能力。"],
    ["竞争跟进", "沉淀行业模板、客户连接器、证据结构和交付经验。"],
  ];
  risks.forEach(([r, m], i) => {
    const y = 128 + i * 86;
    shape(slide, 88, y, 1090, 62, i % 2 ? "#FFF7F7" : C.white, "#E3EAF2", "rect");
    shape(slide, 88, y, 8, 62, [C.red, C.amber, C.blue, C.purple, C.teal][i], "none", "rect");
    text(slide, r, 118, y + 18, 180, 18, { size: 17, bold: true, color: C.ink });
    text(slide, m, 318, y + 16, 800, 22, { size: 16, color: C.muted });
  });
  text(slide, "风险不可怕，关键是让评委看到：成本、市场、合规、交付都有预案。", 138, 598, 940, 24, {
    size: 21,
    bold: true,
    color: C.ink,
    align: "center",
  });
  footer(slide);
  return slide;
}

function slide15(presentation) {
  const slide = presentation.slides.add();
  addBg(slide, true);
  text(slide, "明鉴 MingJian", 76, 86, 520, 60, { size: 50, bold: true, color: C.white });
  text(slide, "让每一次 AI 决策都有据可查、有迹可循。", 80, 160, 560, 34, { size: 26, bold: true, color: "#A7F3D0" });
  text(slide, "本轮希望获得", 82, 250, 240, 28, { size: 24, bold: true, color: C.white });
  const asks = [
    ["试点客户", "投研、竞品分析、风险监控团队"],
    ["模型/算力资源", "API 额度、云服务器、测试账号"],
    ["启动资金", "10-30 万用于产品打磨与市场验证"],
    ["合作渠道", "AI 社区、企业服务、咨询机构"],
  ];
  asks.forEach(([a, b], i) => {
    const x = 82 + (i % 2) * 330;
    const y = 304 + Math.floor(i / 2) * 112;
    const accent = [C.teal, C.blue, C.amber, C.purple][i];
    shape(slide, x, y, 292, 82, "#111D2F", "#5B6B85");
    shape(slide, x, y, 7, 82, accent, "none", "rect");
    text(slide, a, x + 26, y + 17, 230, 20, { size: 17, bold: true, color: accent });
    text(slide, b, x + 26, y + 47, 230, 16, { size: 12.5, color: "#CBD5E1" });
  });
  shape(slide, 770, 104, 360, 360, "#07101F", "#26354F");
  shape(slide, 856, 160, 188, 188, "#111D2F", "#3A4E6E");
  shape(slide, 896, 204, 108, 62, { type: "solid", color: "#0F766E" }, "#A7F3D0", "ellipse");
  shape(slide, 934, 224, 32, 32, "#0B1220", "#D1FAE5", "ellipse");
  text(slide, "明鉴", 894, 286, 112, 38, { size: 34, bold: true, color: C.white, align: "center" });
  text(slide, "谢谢观看", 760, 506, 420, 58, { size: 52, bold: true, color: C.white, align: "center" });
  text(slide, "GitHub: github.com/dashitongzhi/MingJian", 764, 585, 410, 24, { size: 18, color: "#CBD5E1", align: "center" });
  footer(slide, true);
  return slide;
}

function makeContactSheet(previewPaths) {
  const result = spawnSync(PYTHON, [path.join(SKILL_DIR, "scripts/make_contact_sheet.py"), "--output", CONTACT_SHEET, ...previewPaths], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`${result.stdout}\n${result.stderr}`);
  }
}

async function main() {
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  await ensureArtifactToolWorkspace(WORKSPACE);
  const artifact = await importArtifactTool(WORKSPACE);
  const { Presentation, PresentationFile } = artifact;
  const presentation = Presentation.create({ slideSize: { width: W, height: H } });
  const builders = [
    slide01,
    slide02,
    slide03,
    slide04,
    slide05,
    slide06,
    slide07,
    slide08,
    slide09,
    slide10,
    slide11,
    slide12,
    slide13,
    slide14,
    slide15,
  ];
  builders.forEach((fn) => fn(presentation));
  const previewPaths = [];
  for (let i = 0; i < presentation.slides.count; i += 1) {
    const slide = presentation.slides.getItem(i);
    const padded = String(i + 1).padStart(2, "0");
    const png = await presentation.export({ slide, format: "png", scale: 0.8 });
    const out = path.join(PREVIEW_DIR, `slide-${padded}.png`);
    await saveBlobToFile(png, out);
    previewPaths.push(out);
  }
  makeContactSheet(previewPaths);
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(FINAL_PPTX);
  await fs.copyFile(FINAL_PPTX, FINAL_PPTX_V2);
  await fs.copyFile(FINAL_PPTX, FINAL_PPTX_PRICE);
  const stat = await fs.stat(FINAL_PPTX);
  const statV2 = await fs.stat(FINAL_PPTX_V2);
  const statPrice = await fs.stat(FINAL_PPTX_PRICE);
  console.log(JSON.stringify({ output: FINAL_PPTX, outputV2: FINAL_PPTX_V2, outputPrice: FINAL_PPTX_PRICE, bytes: stat.size, bytesV2: statV2.size, bytesPrice: statPrice.size, slides: presentation.slides.count, contactSheet: CONTACT_SHEET }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
