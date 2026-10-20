# 工作区清理记录（2026-10-20）

项目保留程序源码、前端、依赖、部署配置、维护工具和当前运行数据。独立测试、示例、一次性修复脚本、旧备份和过期临时文件已归档到项目外；仍被知识条目或稿件引用的素材与审核记录保留原路径。

本次移出 23,500 个文件，原文件合计约 5.06 GiB。归档前后逐文件核对 SHA256，恢复包约 3.64 GiB。当前 DockerData 中的知识库、账号、商品、稿件、素材和发布包保持原位，后台采集脚本及运行依赖保留。

本机恢复资料：`D:/Workspace/XHS-Downloader-cleanup-20261020/`。`backup.zip` 保存文件原字节，`manifest.json` 保存原路径与哈希，`VERIFICATION.txt` 保存实际执行记录。此私有恢复包不提交 GitHub。

需要测试或示例时，从恢复包提取 `tests/`、`example.py` 或对应脚本。README 及历史文档中的测试命令需在恢复相应脚本后使用。也可在 Git Bash 中执行：

```bash
bash /d/Workspace/XHS-Downloader-cleanup-20261020/ROLLBACK.sh /d/Workspace/XHS-Downloader-restored-files
```

恢复脚本接受目标副本目录，校验归档和文件哈希，并拒绝覆盖内容不同的现有文件。恢复包是清理文件的备份，不是完整程序部署包。

`.gitignore` 排除任务产物、下载素材、依赖目录的运行数据及本地账号工作要求。程序代码和部署配置提交 GitHub；数据库、登录状态、私有配置和恢复包留在本机。

本次未重建运行镜像。本地源码与运行镜像的历史版本关系见 [维护记录](maintenance-20261006.md)。
