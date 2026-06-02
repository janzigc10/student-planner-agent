# Android Packaging Evaluation

## Current PWA Status

当前最小交付形态继续以 PWA 为主。现有配置已经具备 `start_url=/chat`、`display=standalone`、maskable SVG 图标、production service worker、Web Push 订阅页和通知点击回到聊天页的基础能力。

本轮补强点：

- service worker 支持 `SKIP_WAITING`，配合前端注册的 auto update，降低旧缓存长期滞留风险。
- 通知点击会导航现有窗口到 `/chat`，而不是只聚焦任意旧窗口。
- 课表图片上传在异步解析时会给用户明确的后台解析提示。
- Chat 工具进度补齐 task mutation 标签，避免真实 agent loop 执行时显示泛化的“处理中”。

仍不能从本机自动宣称完成的部分是真机安装、桌面图标、独立窗口、冷启动和移动端系统通知展示。这些必须在手机 HTTPS origin 上实测。

## TWA

TWA 适合作为下一步 Android 分发路线，但前提是当前 PWA 的真实手机链路已经稳定。它的优点是改造小、能保留 Web 栈和现有服务端；缺点是仍然依赖 PWA 本身质量，不能解决后端推送出网、agent loop 稳定性或页面状态机问题。

适合启动 TWA 的条件：

- 手机 PWA 安装、启动、更新和通知点击已经通过。
- 核心路径登录、聊天、课表图片导入、日历查看、课程编辑已经能连续自用。
- Web Push 在目标网络环境下可稳定发送并展示。

## Capacitor

Capacitor 只有在明确需要原生能力时才值得引入，例如更强的后台任务、系统级提醒、文件选择兼容兜底或更细的通知控制。当前阶段直接引入 Capacitor 会增加打包、权限、桥接、调试和发布复杂度，容易分散 Agent Loop 与 PWA 稳定性验证。

## Recommendation

当前建议：继续 PWA，不进入 Capacitor；TWA 作为 PWA 稳定后的最小 Android 包装候选。

理由：

- 当前主要风险仍在真实 agent loop、手机 PWA 链路和推送闭环，不在“有没有 APK”。
- PWA 已经覆盖现阶段自用验证所需的入口形态。
- TWA 可以在 PWA 稳定后较低成本承接 Android 安装包诉求。

## Minimum Change Scope

下一步最小范围只做：

- 用 HTTPS 手机入口完成 PWA 安装、启动、更新验证。
- 用真实手机跑登录、聊天、课表图片导入、日历查看、课程编辑。
- 验证通知权限、订阅、测试通知、通知点击回 `/chat`。
- 若上述通过，再建一个单独 TWA 预研 plan。

## Not Doing Yet

- 不现在引入 Capacitor。
- 不为了 Android 包装重写前端壳层。
- 不把 PWA 问题绕过成原生问题。
- 不在手机核心链路未稳定前做正式应用商店发布准备。
