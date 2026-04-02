# polygon2hydro (p2h)

`polygon2hydro`（`p2h`）用于将 Polygon contest package 转换为 Hydro/HydroOJ 可导入的题目包。
输入为一个包含多道题目的 contest zip，输出为“每道题一个 zip”的 Hydro 导入格式。

## 1. 功能概览

- 从 contest 包自动发现 `problems/<slug>/...` 目录。
- 读取题目元数据、题面、测试数据与附件资源。
- 为每道题生成 Hydro 导入包，核心内容包括：
  - `problem.yaml`
  - `problem_zh.md`
  - `testdata/config.yaml`
  - `testdata/testsNN.in/out`
  - `additional_file/*`（若存在）

## 2. 安装与运行

### 2.1 可编辑安装（推荐）

```bash
python3 -m pip install -e .
```

安装后可直接使用：

```bash
p2h convert ...
```

### 2.2 直接以模块方式运行

```bash
PYTHONPATH=src python3 -m p2h.cli convert ...
```

## 3. 命令行接口

```bash
p2h convert <contest_zip> -o <output_dir> --pid-start P1145 [options]
```

### 3.1 参数说明

- `contest_zip`：Polygon contest 包路径。
- `-o, --output`：输出目录（每题输出一个 zip）。
- `--pid-start`：起始 PID（如 `P1145`），后续题目按顺序递增。
- `--owner`：写入 `problem.yaml.owner`，默认 `1`。
- `--tag`：可重复指定，写入 `problem.yaml.tag` 列表。
- `--only`：仅转换指定 slug；支持重复传参或逗号分隔。
- `--run-doall`：执行每题 `doall.sh` 生成测试/答案（默认启用）。
- `--no-run-doall`：跳过 `doall.sh`，仅使用已有测试文件。
- `--verbose`：输出详细日志。

## 4. 使用示例

### 4.1 全量转换

```bash
p2h convert example/polygon-contest-package/contest-56961.zip \
  -o out \
  --pid-start P1000 \
  --owner 1 \
  --tag "UESTCPC 初赛"
```

### 4.2 按 slug 选择性转换

```bash
p2h convert example/polygon-contest-package/contest-56961.zip \
  -o out-only \
  --pid-start P2000 \
  --only buy-cpu \
  --only colorful-path,kettle
```

## 5. 输出结构示例

```text
题目名.zip
└── 1/
    ├── problem.yaml
    ├── problem_zh.md
    ├── testdata/
    │   ├── config.yaml
    │   ├── tests01.in
    │   ├── tests01.out
    │   └── ...
    └── additional_file/
        └── ...
```

## 6. 题面转换说明

当前题面转换优先使用 `statement-sections/chinese` 的结构化内容，并输出如下模板：

- `# Description`
- `# Format`
  - `## Input`
  - `## Output`
- `# Samples`（`input1/output1`, `input2/output2`, ...）
- `# Note`

图片会尽量转换为 Hydro 常用格式，例如：

```html
<center>
<img src="file://1.png"/>
</center>
```

以及带宽度参数的形式：

```html
<center>
<img src="file://1.png" width="80%" />
</center>
```

## 7. 安全说明

`--run-doall` 会执行 contest 包中的 `doall.sh` 及相关脚本。
请仅对**可信来源**的输入包启用该选项，避免对不受信任压缩包直接执行脚本。

## 8. 常见错误

- `unknown slug(s): ...`：`--only` 指定的 slug 不存在于 contest 包中。
- `missing answer for test index ...`：缺少 `.a` 答案文件；可启用 `--run-doall` 或先在 Polygon 侧生成测试。
- `missing problem.xml`：题目目录结构不完整。

## 9. 测试

```bash
python3 -m pytest -q
```

若当前环境未安装 `pytest`，可先安装测试依赖后再执行。