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
    state: {
      retry: "重试",
      loadingTitle: "正在加载",
      loadingBody: "正在从后端读取最新数据。",
      errorTitle: "无法加载数据",
      permissionTitle: "权限不足",
      permissionBody: "当前身份没有访问此资源的权限，请切换角色或联系管理员。",
      dashboardErrorBody: "无法读取工单队列。请确认后端服务可用，然后重试。",
      dashboardApprovalsErrorBody: "无法读取审批数量。工单队列仍可查看，请稍后重试审批数据。",
      ticketsEmptyTitle: "暂无工单",
      ticketsEmptyBody: "创建第一张工单后，队列和指标会显示真实运行数据。",
      approvalsEmptyTitle: "暂无待审批项",
      approvalsEmptyBody: "需要人工处理的回复草稿会出现在这里。",
      approvalsErrorBody: "无法读取审批队列。请确认服务状态或当前角色权限。",
      ticketErrorBody: "无法读取这张工单。请确认工单存在、租户权限正确并重试。",
      runErrorBody: "工单已读取，但无法读取最近运行的追踪数据。",
      noRunBody: "启动一次 Agent 运行后，这里会显示当前节点、风险和追踪入口。",
      traceErrorBody: "无法读取运行追踪。请确认运行存在、后端服务可用并重试。",
      stepsEmptyTitle: "暂无步骤",
      stepsEmptyBody: "运行开始后，Agent 步骤会按时间线展示。",
      toolsEmptyTitle: "暂无工具调用",
      toolsEmptyBody: "本次运行没有记录工具调用。",
      evidenceEmptyTitle: "暂无证据",
      evidenceEmptyBody: "检索命中的知识库证据会显示在这里。"
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
      rejectedNote: "需要人工改写",
      startFailed: "启动运行失败",
      decisionFailed: "提交审批决定失败"
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
    state: {
      retry: "Retry",
      loadingTitle: "Loading",
      loadingBody: "Reading the latest data from the API.",
      errorTitle: "Unable to load data",
      permissionTitle: "Permission required",
      permissionBody: "Your current identity cannot access this resource. Switch roles or contact an administrator.",
      dashboardErrorBody: "Unable to read the ticket queue. Check that the API is available, then retry.",
      dashboardApprovalsErrorBody: "Unable to read approval counts. The ticket queue is still available; retry approval data later.",
      ticketsEmptyTitle: "No tickets yet",
      ticketsEmptyBody: "Create the first ticket to populate the queue and live metrics.",
      approvalsEmptyTitle: "No pending approvals",
      approvalsEmptyBody: "Reply drafts that need human review will appear here.",
      approvalsErrorBody: "Unable to read the approval queue. Check service health or role permissions.",
      ticketErrorBody: "Unable to read this ticket. Confirm it exists, your tenant can access it, then retry.",
      runErrorBody: "The ticket loaded, but its latest run trace could not be read.",
      noRunBody: "Start an agent run to show the current node, risk, and trace entry here.",
      traceErrorBody: "Unable to read this run trace. Confirm the run exists and the API is available, then retry.",
      stepsEmptyTitle: "No steps yet",
      stepsEmptyBody: "Agent steps will appear on the timeline after a run starts.",
      toolsEmptyTitle: "No tool calls",
      toolsEmptyBody: "This run has no recorded tool calls.",
      evidenceEmptyTitle: "No evidence",
      evidenceEmptyBody: "Retrieved knowledge evidence will appear here."
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
      rejectedNote: "Needs manual rewrite",
      startFailed: "Start run failed",
      decisionFailed: "Submit decision failed"
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
