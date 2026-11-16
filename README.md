# CalabiyauUID

<p align="center">
  <a href="ICON.png">
    <img src="ICON.png" width="162" height="162" alt="CalabiyauUID">
  </a>
</p>
<h1 align="center">CalabiyauUID 0.1.0</h1>
<h4 align="center">基于 gsuid_core 的 全功能卡拉彼丘插件</h4>

<p align="center">
  <a href="https://www.python.org/" target="_blank"><img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python 3.12+"></a>
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank"><img src="https://img.shields.io/badge/gsuid_core-0.11.0+-orange" alt="gsuid_core 0.11.0+"></a>
</p>

<div align="center">
  <a href="https://docs.sayu-bot.com/" target="_blank">安装文档</a> &nbsp; · &nbsp;
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank">gsuid_core</a>
</div>

## 丨安装提醒

> **注意：该插件为 [早柚核心(gsuid_core)](https://github.com/Genshin-bots/gsuid_core) 的扩展，具体安装方式可参考上方安装文档**
>
> 🚧 项目快速迭代中，有漏洞可提issue或pr 🚧

> [!TIP]
> 国际服接口由于编写时接口不在线，将在后续接口稳定后加入（也欢迎提交PR）

## 丨命令列表

<details><summary>账号绑定</summary>

| 命令 | 说明 |
|------|:------:|
| `kq绑定 1234567` | 绑定卡拉彼丘国服账号并拉取首次战绩 |
| `kq解绑 1234567` | 解绑已绑定的卡拉彼丘账号 |
| `kq查看` | 查看当前已绑定的卡拉彼丘账号 |
| `kq切换 1234567` | 切换当前主账号，不传参默认切至下一个 |

</details>

<details><summary>战绩查询</summary>

| 命令 | 说明 |
|------|:------:|
| `kq战绩总览` | 查看当前账号的生涯总览卡片 |
| `kq战绩总览 1234567` | 查看 12345678 的生涯总览 |
| `kq历史战绩` | 查看当前绑定账号最近的对局 |
| `kq刷新数据 1234567` | 拉取玩家 1234567 的最新数据 |
| `kq回放下载 123456789012345678` | 获取指定对局 ID 的回放文件 |

</details>

<details><summary>排行查询</summary>

| 命令 | 说明 |
|------|:------:|
| `kq排位排行` | 查看当前赛季排位段位排行榜 |
| `kq团队排行` | 查看团队乱斗排行榜 |
| `kq推进排行` | 查看极限推进排行榜 |
| `kq挑战排行` | 查看挑战排行榜 |
| `kq感染排行` | 查看晶源感染排行榜 |
| `kq角色[排位\|全部][出场率\|胜率]排行` | 查看全角色出场率与胜率统计榜 |
| `kq超弦体排行 糖猫` | 查看指定角色的玩家排行榜 |

</details>

<details><summary>社区动态</summary>

| 命令 | 说明 |
|------|:------:|
| `kq活跃图` | 查看玩家活跃趋势卡片 |
| `kq世界聊天` | 查看世界频道实时聊天 |

</details>

<details><summary>其他</summary>

| 命令 | 说明 |
|------|:------:|
| `kq帮助` | 显示插件帮助图 |

</details>

## 丨其他

- 本项目仅供学习使用，请勿用于商业用途
- [GPL-3.0 License](LICENSE)
- 若 issue 回复不及时，请进群 [929275476](https://qm.qq.com/cgi-bin/qm/qr?k=d1oNQ1wePPbCkhPbP3vZN-DsXDD0hG61&authKey=0PdxKz%2BMbWgy7kwcF9OB%2B%2BrgOWKuREFG6tgJuWpr%2BzN8gtBTlGR6wDbk6N0W3bL1&noverify=0&group_code=929275476) @我

## 致谢
| 贡献者 | 引用 |
|:------:|:------:|
| [Wuyi 无疑](https://github.com/KimigaiiWuyi) | 框架作者 |
| [gsuid_core](https://github.com/Genshin-bots/gsuid_core) | 插件依赖框架 |
| [dakanu](https://www.dakanu.com/) | 数据查询接口 |
| [白泉幽奈](https://space.bilibili.com/2198) | 数据接口作者 |
| [卡拉彼丘表情包](https://wiki.biligame.com/klbq/%E8%A1%A8%E6%83%85%E5%8C%85) | 帮助图和部分图片表情来源 |
