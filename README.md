# polygon2hydro (p2h)

`polygon2hydro`（`p2h`）用于将 Polygon contest package 转换为 Hydro/HydroOJ 可导入的题目包。
输入为一个包含多道题目的 contest zip，输出为“每道题一个 zip”的 Hydro 导入格式。

支持传统题与交互题；Windows 与 Linux/macOS 均可使用。纯标准库实现，Python ≥ 3.10。

## 安装

```bash
python3 -m pip install -e .
```

不安装也可以直接运行：

```bash
PYTHONPATH=src python3 -m p2h.cli convert ...
```

## 转换

```bash
p2h convert contest-56961.zip -o out --pid-start P1000
```

| 参数 | 说明 |
| --- | --- |
| `contest_zip` | Polygon contest 包 |
| `-o, --output` | 输出目录，每题一个 zip |
| `--pid-start` | 起始 PID（如 `P1000`），后续题递增 |
| `--owner` | 题目上传者 id，默认 `1` |
| `--tag` | 题目标签，可重复 |
| `--only` | 只转指定 slug，可重复或用逗号分隔 |
| `--no-run-doall` | 不执行包内构建脚本，直接用已有测试 |
| `--verbose` | 输出详细日志 |

常用：

```bash
# 带标签全量转换
p2h convert contest-56961.zip -o out --pid-start P1000 --tag "校赛" --tag "2026"

# 只转部分题目
p2h convert contest-56961.zip -o out --pid-start P2000 --only buy-cpu --only kettle,magic
```

默认会执行包内的构建脚本（`doall`）生成测试与答案。**只对可信来源的包启用**；`--no-run-doall` 可跳过。

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
    │   ├── check.cpp
    │   └── ...
    └── additional_file/
        ├── 1.png
        └── legend.tex
```

把每个 zip 直接导入 Hydro 即可。同名题目不会覆盖，会依次命名为 `题目名 (2).zip`。

## 单独转题面

```bash
# 转单个文件，输出到 stdout
p2h statement-md problems/a/statements/chinese/problem.html

# 转 TeX 片段（如 legend.tex）
p2h statement-md problems/a/statement-sections/chinese/legend.tex --type tex-block -o legend.md

# 转整题（需目录内有 problem.xml），默认写入 problem_zh.md
p2h statement-md problems/a
```

## 环境要求

| 环境 | 构建脚本 | 额外依赖 |
| --- | --- | --- |
| Windows | `doall.bat` | 无 |
| Linux / macOS | `doall.sh` | `wine`（个别题目还需 `java`） |

`--verbose` 会打印本机使用的入口。转换结果在两个平台上完全一致。

## 常见问题

- `unknown slug(s)`：`--only` 里的 slug 不在包中。
- `missing answer for test key ...`：缺答案文件，确认构建脚本能正常执行，或先在 Polygon 侧生成测试。
- 交互题在受限环境（服务账户、CI 沙箱）构建失败时，会自动改用包内的 `CrossRun.jar`，需要 `java`。
- 无效 zip、未知 slug 等错误返回退出码 `1`；命令行参数错误返回 `2`。
