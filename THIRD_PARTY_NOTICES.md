# Third-party notices

Yutong Agent Teams is a Python implementation of a small, local-first agent collaboration workspace. CCCC is a design reference for groups, durable messages, explicit delivery state, idempotent sends and bounded coordination. This is not an official CCCC distribution and does not include its Rust service, frontend, logo or cloud services.

- CCCC: https://github.com/ChesterRa/cccc — Apache License 2.0. Full license in `licenses/CCCC-Apache-2.0.txt`.
- The CCU Agent frontend informs the layout and visual tokens. The runtime bridge calls the user's existing CCU project; it is not bundled.
- The automotive-agent bridge calls the user's existing MATLAB project and MathWorks SDK. MATLAB, Simulink, SDK/toolkits and associated tools are not bundled. They retain their own license and installation requirements.
- Claude Code and DeepSeek Harness are invoked as separately installed runtimes, under their own licenses and account terms. No provider credentials are included.
- Tencent ADP is called via its published HTTP SSE API; the service is not bundled.
- PyYAML 6.0.2 parses Harness model settings (MIT); the full license is in `licenses/PyYAML-MIT.txt`.
- Agent identity icons are local assets, not network-loaded UI resources: Claude from Simple Icons (CC0), MATLAB from Devicon (MIT), CCU from the user's own project, and DeepSeek's favicon from its official chat site. Full library notices are in `licenses/simple-icons-CC0.txt` and `licenses/devicon-MIT.txt`; asset provenance is in `assets/brand/agent-icons.md`. Brand marks identify the corresponding integrations and retain their respective ownership.

The EXE bundles CPython and dependencies including pywebview (BSD), httpx/httpcore (BSD), pythonnet (MIT), clr-loader (MIT), proxy_tools (upstream BSD notice), CFFI (MIT), Bottle (MIT), AnyIO (MIT), Certifi (MPL-2.0), and their transitive dependencies. Available full upstream license notices are preserved in `licenses/` and embedded in the executable. PyInstaller has a bootloader distribution exception; its license is also included.

The WebView2 SDK bridge/loader DLLs supplied by pywebview are bundled; Microsoft WebView2 SDK 1.0.2957.106 LICENSE and NOTICE files are included from its NuGet package. The WebView2 browser runtime and .NET Framework remain system prerequisites. Microsoft's components retain their own terms and are not relicensed by this project.

The original Python/JavaScript implementation is supplied to the user's internal project. This notice does not assign a public license to the user's proprietary code or grant rights in third-party products and trademarks.
