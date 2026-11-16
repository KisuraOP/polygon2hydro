# polygon2hydro (p2h)

`polygon2hydro`（`p2h`）用于将 Polygon contest package 转换为 Hydro/HydroOJ 可导入的题目包。
输入为一个包含多道题目的 contest zip，输出为“每道题一个 zip”的 Hydro 导入格式。

支持传统题、交互题与通信题（run-twice，要求包内自带 interactor）；Windows 与 Linux/macOS 均可使用。纯标准库实现，Python ≥ 3.10。

## 安装

```bash
python3 -m pip install -e .
```

不安装也可以直接运行：

```bash
# Linux / macOS
PYTHONPATH=src python3 -m p2h.cli convert ...
# Windows PowerShell
$env:PYTHONPATH="src"; python -m p2h.cli convert ...
```

## 转换

```bash
p2h convert contest-56961.zip -o out --pid-start P2000
```

| 参数 | 说明 |
| --- | --- |
| `contest_zip` | Polygon contest 包 |
| `-o, --output` | 输出目录，每题一个 zip |
| `--pid-start` | 起始 PID（如 `P2000`），后续题递增 |
| `--owner` | 题目上传者 id，默认 `1` |
| `--tag` | 题目标签，可重复 |
| `--only` | 只转指定 slug，可重复或用逗号分隔 |
| `--no-run-doall` | 不执行包内构建脚本，直接用已有测试；通信题需要构建阶段重算答案，不建议跳过 |
| `--missing-env` | 缺少构建工具时的行为：`warn`（默认）/ `ask` / `error` |
| `--interactive-runner` | 交互题答案生成：`auto`（默认，包内脚本失败时回退 `CrossRun.jar`）/ `package`（只用包内脚本）/ `crossrun`（只用 `CrossRun.jar`） |
| `--verbose` | 输出详细日志（含本机使用的构建入口） |

常用：

```bash
# 带标签全量转换
p2h convert contest-56961.zip -o out --pid-start P2000 --tag "校赛" --tag "2026"

# 只转部分题目
p2h convert contest-56961.zip -o out --pid-start P2000 --only buy-cpu --only kettle,magic
```

默认会执行包内的构建脚本（`doall`）生成测试与答案，**只对可信来源的包启用**；
`--no-run-doall` 可跳过。某题失败时会逐条列出原因并继续处理其它题，退出码为 `1`；
命令行参数错误退出码为 `2`。其它选项见 `p2h convert --help`。

## 输出

```text
题目名.zip
└── 1/
    ├── problem.yaml
    ├── problem_zh.md
    ├── testdata/
    │   ├── config.yaml
    │   ├── 01.in
    │   ├── 01.out
    │   ├── checker.cpp
    │   └── ...
    └── additional_file/
        └── 1.png
```

把每个 zip 直接导入 Hydro 即可。同名题目不会覆盖，会依次命名为 `题目名 (2).zip`。
`testdata/` 除测试点外，还带上包内声明的 checker/interactor 等可执行文件与标程源码。
`additional_file/` 放题面资产（图片、样例文件等）与包内 `attachments/`；题面 `.tex` 源文件只用于转换，不会打包进去。

## 单独转题面

```bash
# 转单个文件，输出到 stdout
p2h statement-md problems/a/statements/chinese/problem.html

# 转 TeX 片段（如 legend.tex）
p2h statement-md problems/a/statement-sections/chinese/legend.tex --type tex-block -o legend.md

# 转整题（需目录内有 problem.xml），默认写入 problem_zh.md
p2h statement-md problems/a
```

`--lang` 只在整题目录模式下生效，`--type` 只在单文件模式下生效。

## 环境要求

| 环境 | 构建脚本 | 额外依赖 |
| --- | --- | --- |
| Windows | `doall.bat` | 交互题回退到 `CrossRun.jar` 时需要 `java` |
| Linux / macOS | `doall.sh` | `wine`；交互题走 `CrossRun.jar` 时还需要 `java` |

两平台的产物内容一致（逐条目相同）。
