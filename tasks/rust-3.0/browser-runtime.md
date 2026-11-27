# Chrome in Reverie

在桌面会话的右侧工作面板打开「浏览器」，可查看和切换该项目、该会话的标签。模型工具支持打开、列出、观察、导航、点击、输入、按键、滚动和关闭。观察返回主文档与开放 shadow root 中可见的元素、视口和 PNG 的身份。PNG 保存在执行工作区的 `.reverie/browser/observations/`。每次操作都要使用对应标签最新观察返回的目标。

桌面设置中的「浏览器配置」支持专用持久配置和仅本次运行。终端可输入 `/browser-profile persistent` 或 `/browser-profile ephemeral`。持久配置保留网站数据。标签的模型操作权属于创建它的运行。临时标签随运行结束关闭。桌面中已完成的持久标签可以继续由用户查看和关闭。

独立 CLI 在安装目录查找对应的 `ReverieUI` 程序。首次实际使用浏览器时，CLI 才启动组件。单独安装 CLI 时，可将环境变量 `REVERIE_BROWSER_COMPONENT` 设为已安装的 ReverieUI 可执行文件的绝对路径。CLI 使用自己的配置目录，结束时关闭组件。独立 CLI 的持久目录位于 Reverie 应用数据下的 `.reverie/browser-component/persistent`。同一持久目录同时只能由一个组件使用。

SDK 宿主注册、请求完成、标签失效和撤销在私有控制通道完成。独立进程使用回环连接和每次启动生成的一次性凭据。网页使用专用 Electron Session、沙箱、上下文隔离，页面内容作为外部输入。浏览器工具沿用正常会话的审批。显式只读允许列出标签，观察会写入 PNG，网页操作会产生副作用，二者都需要写权限。

## Windows 功能验收

- 桌面检查驱动真实的生产 renderer、preload、Electron Chromium、Rust release 和回环模型。验证可见的原生侧栏、中文输入、点击后正文回读、过期目标拒绝、PNG、标签导航、Tab 焦点、120 个 CSS 像素的实际滚动位移，以及取消进行中的网络连接。
- Windows 解包应用曾能回读网页，但侧栏仍为空白。修复后同时核对网页的 `document.visibilityState`、实际应用窗口归属及侧栏屏幕像素。测试页底色为 RGB(82, 199, 132)，屏幕采样精确相符。窗口缩略图有轻微色差，在侧栏取样区域有 215,625 个像素各通道误差不超过 3。
- 独立 CLI 检查运行解包产品中的原生程序，另外启动三次 CLI，以网页回读验证持久数据和临时隔离，并检查进程返回后临时目录已经清除。
- 验收使用本地表单与回环模型。公网模型的自主选择、真实登录、跨源 iframe 内部输入、上传下载、前进后退、刷新和四平台发行验收继续列在[未验证清单](UNVERIFIED.md)。
- 本机从 D 盘构建目录直接启动解包应用时，Chromium GPU 子进程退出，错误码为 `0x80000003`。相同程序和资源复制到 G 盘项目的验证目录后通过独立 CLI 验收。两处目录的访问控制不同；具体触发条件仍待定位，验收保留 Chromium 沙箱。

从仓库根目录复验。先完成 Rust release 和桌面生产构建；独立 CLI 验收使用带有 ReverieUI 及内置资源的解包目录。

```text
node ReverieCli-ui/node_modules/electron/cli.js scripts/verification/rust-browser-electron-smoke.cjs <cargo-target>/release/reverie.exe <evidence-directory>
node scripts/verification/rust-browser-cli-smoke.mjs <unpacked-directory>/reverie.exe <evidence-directory>
```
