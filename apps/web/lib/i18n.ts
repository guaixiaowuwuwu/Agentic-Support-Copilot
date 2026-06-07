export const locales = ["zh", "en"] as const;
export type Locale = (typeof locales)[number];

export const localeCookieName = "support-copilot-locale";
export const defaultLocale: Locale = "zh";

export function normalizeLocale(value?: string | null): Locale {
  return value === "en" || value === "zh" ? value : defaultLocale;
}

export const dictionaries = {
  zh: {
    languageName: "中文",
    otherLanguageName: "English",
    nav: {
      tickets: "工单",
      approvals: "审批",
      trace: "追踪"
    },
    languageToggle: {
      ariaLabel: "切换语言",
      title: "切换到英文"
    },
    common: {
      run: "运行",
      trace: "追踪",
      review: "审批",
      approval: "审批",
      finalReply: "最终回复",
      openRunTrace: "打开运行追踪",
      openApprovalQueue: "打开审批队列"
    },
    dashboard: {
      eyebrow: "私有化支持运营",
      title: "工单",
      openApprovals: "打开审批",
      metricsLabel: "仪表盘指标",
      totalTickets: "工单总数",
      awaitingApproval: "待审批",
      pendingApprovals: "待处理审批",
      replied: "已回复",
      newTicket: "新建工单",
      queue: "队列",
      tableSubject: "主题",
      tableStatus: "状态",
      tablePriority: "优先级",
      tableUpdated: "更新时间"
    },
    ticketForm: {
      tenant: "租户",
      customer: "客户",
      channel: "渠道",
      subject: "主题",
      description: "描述",
      defaultCustomer: "Acme Customer",
      defaultSubject: "API 报 401",
      defaultDescription: "客户说 API 报 401，帮我排查并回复。request_id=req_123",
      createTitle: "创建工单并运行智能体",
      create: "创建 + 运行",
      running: "运行中",
      createFailed: "创建工单失败"
    },
    ticketDetail: {
      ticket: "工单详情",
      tenant: "租户",
      channel: "渠道",
      priority: "优先级",
      type: "类型",
      updated: "更新时间",
      currentRun: "当前运行",
      node: "节点",
      risk: "风险",
      noRun: "暂无运行"
    },
    runActions: {
      startRun: "启动运行",
      running: "运行中",
      startRunTitle: "启动 Agent 运行",
      approve: "批准",
      reject: "驳回",
      approveTitle: "批准回复",
      rejectTitle: "驳回回复",
      approvedNote: "已从仪表盘批准",
      rejectedNote: "需要人工改写"
    },
    approvals: {
      eyebrow: "人工审批",
      title: "审批队列"
    },
    trace: {
      title: "运行追踪",
      metricsLabel: "运行指标",
      currentNode: "当前节点",
      latency: "耗时",
      evidence: "检索证据",
      tokens: "Token",
      agentSteps: "Agent 步骤",
      verifier: "校验器",
      toolCalls: "工具调用"
    },
    status: {
      open: "待处理",
      running: "运行中",
      triaged: "已分诊",
      awaiting_approval: "待审批",
      replied: "已回复",
      rejected: "已驳回",
      pending: "待处理",
      approved: "已批准",
      success: "成功",
      blocked: "已阻断",
      denied: "已拒绝",
      failed: "失败",
      low: "低",
      medium: "中",
      high: "高"
    }
  },
  en: {
    languageName: "English",
    otherLanguageName: "中文",
    nav: {
      tickets: "Tickets",
      approvals: "Approvals",
      trace: "Trace"
    },
    languageToggle: {
      ariaLabel: "Switch language",
      title: "Switch to Chinese"
    },
    common: {
      run: "Run",
      trace: "Trace",
      review: "Review",
      approval: "Approval",
      finalReply: "Final reply",
      openRunTrace: "Open run trace",
      openApprovalQueue: "Open approval queue"
    },
    dashboard: {
      eyebrow: "Private support operations",
      title: "Tickets",
      openApprovals: "Open approvals",
      metricsLabel: "Dashboard metrics",
      totalTickets: "Total tickets",
      awaitingApproval: "Awaiting approval",
      pendingApprovals: "Pending approvals",
      replied: "Replied",
      newTicket: "New ticket",
      queue: "Queue",
      tableSubject: "Subject",
      tableStatus: "Status",
      tablePriority: "Priority",
      tableUpdated: "Updated"
    },
    ticketForm: {
      tenant: "Tenant",
      customer: "Customer",
      channel: "Channel",
      subject: "Subject",
      description: "Description",
      defaultCustomer: "Acme Customer",
      defaultSubject: "API returns 401",
      defaultDescription: "Customer reports API 401 errors. Please investigate and draft a reply. request_id=req_123",
      createTitle: "Create ticket and run agents",
      create: "Create + Run",
      running: "Running",
      createFailed: "Create ticket failed"
    },
    ticketDetail: {
      ticket: "Ticket",
      tenant: "Tenant",
      channel: "Channel",
      priority: "Priority",
      type: "Type",
      updated: "Updated",
      currentRun: "Current run",
      node: "Node",
      risk: "Risk",
      noRun: "No run yet."
    },
    runActions: {
      startRun: "Start run",
      running: "Running",
      startRunTitle: "Start agent run",
      approve: "Approve",
      reject: "Reject",
      approveTitle: "Approve reply",
      rejectTitle: "Reject reply",
      approvedNote: "Approved from dashboard",
      rejectedNote: "Needs manual rewrite"
    },
    approvals: {
      eyebrow: "Human approval",
      title: "Approval Queue"
    },
    trace: {
      title: "Trace",
      metricsLabel: "Run metrics",
      currentNode: "Current node",
      latency: "Latency",
      evidence: "Evidence",
      tokens: "Tokens",
      agentSteps: "Agent steps",
      verifier: "Verifier",
      toolCalls: "Tool calls"
    },
    status: {
      open: "open",
      running: "running",
      triaged: "triaged",
      awaiting_approval: "awaiting approval",
      replied: "replied",
      rejected: "rejected",
      pending: "pending",
      approved: "approved",
      success: "success",
      blocked: "blocked",
      denied: "denied",
      failed: "failed",
      low: "low",
      medium: "medium",
      high: "high"
    }
  }
} as const;

export type Dictionary = (typeof dictionaries)[Locale];

export function statusLabel(value: string | null | undefined, locale: Locale): string {
  if (!value) {
    return locale === "zh" ? "未知" : "unknown";
  }
  return dictionaries[locale].status[value as keyof (typeof dictionaries)[Locale]["status"]] ?? value.replaceAll("_", " ");
}
