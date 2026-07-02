---
name: pixcake-use
description: 只读探测本地 PixCake 修图应用的数据：给文件和 SQLite 库抓快照、在一次界面操作前后做 diff 以逆出调色参数（pf 参数）的含义、用经过验证的参数码本解读 palette JSON、从 RAW 原图解码预览、离线近似渲染调色效果、给自己照片的编辑记录套 recipe（写前自动备份）。当用户要分析 PixCake 的参数格式、导出/预览自己照片的调色、或把某个滑块对应到 pf 编号时使用。仅针对用户自己的账号和照片；全程只读 PixCake 数据，不解密 FXIP，不绕过登录/付费/签名。macOS。
---

# pixcake-use

只读探测本地 PixCake：快照 → 界面操作 → diff，把"某个滑块对应哪个 `pf`"逆出来；配套已验证的
参数码本、RAW 预览解码和离线近似渲染。

**安装 / 自愈：** 纯 Python 标准库，没有可执行文件时从源码跑：

```sh
git clone https://github.com/leeguooooo/pixcake-use && cd pixcake-use
python3 -m pixcake_use doctor        # 检测 PixCake 路径与运行状态
pip install -e '.[render]'           # 可选：photos --graded 离线渲染需要 Pillow + numpy
```

## 核心命令

```sh
python3 -m pixcake_use snapshot --name before      # 抓快照
python3 -m pixcake_use diff snapshots/before.json snapshots/after.json
python3 -m pixcake_use watch --seconds 30 --name exposure-plus   # 定时窗口内比对一次操作
python3 -m pixcake_use photos                      # 列出照片：位置/id/是否已编辑/recipe 摘要
python3 -m pixcake_use photos --extract previews --graded        # 导出 JPEG + 近似调色预览
python3 -m pixcake_use params <project.db> presets_config_detail --id 2   # 提取 pf 参数
python3 -m pixcake_use apply-current-record <project.db> --thumbnail-id 1 --recipe <recipe.json>
```

参数码本在 `src/pixcake_use/codebook.py`（曝光 3000、对比 3002、HSL 91170–91193 等，
分"应用自标注"和"watch/diff 实测"两类来源，README 有完整表）。

## 边界（不可越）

- 默认只读：SQLite 一律 `mode=ro`。只有 `apply-recipe` / `apply-current-record` 写用户自己
  照片的编辑参数，且写前自动备份整个 SQLite family 和 palette 文件。
- 不解密 FXIP 加密容器（预览缓存 / 相机 LUT）。
- PixCake 运行中时 WAL 未提交帧读不到——要干净的 diff：退出 PixCake → 操作 → 重开 → 抓快照
  （`doctor`/`snapshot`/`watch` 检测到进程会向 stderr 报警）。
