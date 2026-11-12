# 03-changeflow（变流）

Changeflow — CDC / 变更流落库：事件入账 → 序/缺口裁决 → 幂等应用到 sink → 游标提交与对账。

**不是** Feed 多源归并（Feedstitch），**不是** 作业依赖编排（Batchgate）。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5300 |
| API | http://localhost:10300 |

本地开发（可选）：

```bash
# backend
cd backend && pip install -r requirements.txt
set DATA_DIR=..\data
uvicorn app.main:app --reload --port 10300

# frontend
cd frontend && npm install && npm run dev
```

## 主链

配置变更流与夹具 → 触发 Apply → 按序应用 / 缺口隔离 → Sink + 游标 + 运行报告对账

## 采集巡检（本机 CDC 目录 → 采集任务 → 入账 → 应用）

运行「采集巡检」页，或直接调 API：

```bash
# 巡检仓库内演示目录（3 个连续序分片，共 8 条事件）
curl -X POST http://localhost:10300/api/harvest/tasks \
  -H 'Content-Type: application/json' \
  -d '{"source_dir":"harvest_demo","auto_apply":true}'
```

链路：**扫描本机目录里的 `*.jsonl` 分片** → 生成采集任务 + 分片清单（sha256/大小/seq 范围/状态）
→ 解析成功的事件写入变更账本（`disposition=collected`）→ 复用同一 Apply 引擎按连续序应用
（`applied` / `skipped_duplicate` / `quarantine_gap`）。采集本身**不写 Sink**，缺口仍进隔离区。

要点：

- 只接受本机目录，且必须在允许根内（仓库 `backend/app/fixtures`、`DATA_DIR`，可用 `HARVEST_ROOTS` 追加）；
  不支持远程对象存储 / 网络爬取。
- 去重：同内容分片（sha256 相同，含同一次巡检内的重复文件）标记 `skipped_duplicate` 并记录 `duplicate_of`，
  不入账、不算成功；同相对路径内容变化则作为新分片采集并备注 `same_name_new_content`。
- 落库事件在 `change_ledger` 上标记 `harvest_task_id/harvest_shard_id`；Apply run 记录 `harvest_task_id`，
  采集任务记录 `apply_run_id`，三者同源可追溯。
- 对账（任务详情 `reconciliation`）逐项校验：分片状态数 = 发现文件数；采集事件数 = 任务报告 = 账本行数；
  账本 disposition 合计 = `collected + applied + quarantine_gap + skipped_duplicate`；
  每个 Apply 的 `applied + quarantined + skipped + pending_not_applied = loaded`；
  并给出本流 Sink 行数、Sink delta、任务后游标。全部为真才 `balanced=true`。
- 任务、分片、账本、Apply 都落 SQLite，刷新 / 重启后仍可查。

演示目录（`backend/app/fixtures/`）：

| 目录 | 用途 |
| --- | --- |
| `harvest_demo` | 3 个连续序分片（seq 1–8），首跑全部 applied、游标到 8 |
| `harvest_demo_dupes` | 同内容分片×2，演示同次巡检内去重 |
| `harvest_demo_gap` | 缺 seq 2，演示采集成功后应用缺口中止 + 隔离 |
| `harvest_demo_gap_fill` | 后续补采缺失 seq 2 的分片 |
| `harvest_demo_mixed` | 3 个坏分片，演示失败计数与对账仍平衡 |
| `harvest_demo_overlap` | 跨分片重复 seq，演示同批重叠拒收 |
| `harvest_demo_empty` | 无 .jsonl 分片，演示 empty 任务 |

## 种子说明

- **Orders CDC（clean）**：JSONL，seq 1→5 连续 upsert/delete，首跑应全部应用、游标推进到 5。
- **Inventory CDC（clean）**：JSONL，seq 1→3 连续 upsert，独立实体键，用于第二路流演示。
- **Harvest CDC（clean）**：采集专用流，其口径由采集任务入账，不直接绑定夹具文件。

打开「采集巡检」对 `harvest_demo` 跑一次，再用「应用台」/Sink/游标核对；也可在「应用台」对夹具流跑一次做对照。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现，见题单）

当前仓库已实现「连续序幂等应用」主链与本机目录采集巡检；缺口等待/跳过、乱序缓冲、事务整批、双 sink 部分失败、毒丸选择性跳过等均在 `backend/app/modules/*` 留空包，按题单逐题换主链路实现。
