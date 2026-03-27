# OpenClaw Offer Radar

![OpenClaw Offer Radar](./assets/banner.svg)

> 一个优先服务中文 Gmail 与 iPhone 提醒场景的 OpenClaw Skill：帮助用户从招聘邮件里提取真正重要的事件信息。

[![Skill](https://img.shields.io/badge/OpenClaw-Skill-0f172a?style=flat-square)](./SKILL.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square)](./scripts/recruiting_sync.py)
[![Chinese First](https://img.shields.io/badge/Language-中文优先-16a34a?style=flat-square)](./README.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](./LICENSE)

## 这是什么

`OpenClaw Offer Radar` 是一个面向中文用户的招聘邮件处理 skill。

它当前聚焦一条很明确的链路：

`招聘邮件 -> 重要事件识别 -> 提醒体验`

## 使用场景

适合这些情况：

- 你用 Gmail 接收校招、实习、社招相关邮件
- 邮件里会出现面试、笔试、在线测评、授权、补充材料等信息
- 你希望 OpenClaw 帮你把真正重要的事件整理出来
- 你希望重要事件最终能进入更适合日常查看和提醒的地方，比如 iPhone 提醒事项

## 需求说明

这个 skill 主要解决的是下面这类真实需求：

- 招聘邮件很多，但真正重要的是“什么时候面试、什么时候笔试、什么时候截止”
- 同一个事件可能会收到多封邮件，包括邀请、更新、确认、提醒
- 有些邮件只是投递成功或流程通知，不应该进入提醒事项
- 提醒事项里应该保留中文标题、关键时间和有效链接，而不是一堆无关信息

这个仓库当前先聚焦招聘邮件这一条高价值场景，后续会继续往更普适的方向演进。

## 当前范围

目前 README 只保留高层信息，因为识别规则、接入方式和实现细节都还会继续调整。

当前重点是：

- Gmail 招聘邮件筛选
- 面试 / 笔试 / 测评 / 授权类事件识别
- 中文事件整理
- 提醒事项同步

## 快速开始

当前示例环境：

- macOS
- Gmail
- Apple Mail
- Apple Reminders
- `gog`

运行一次扫描：

```bash
python3 scripts/recruiting_sync.py \
  --account your@gmail.com \
  --mail-account 谷歌
```

同步到提醒事项：

```bash
python3 scripts/recruiting_sync.py \
  --account your@gmail.com \
  --mail-account 谷歌 \
  --sync-reminders
```

## 仓库结构

```text
openclaw-offer-radar/
├── README.md
├── SKILL.md
├── LICENSE
├── agents/
├── assets/
└── scripts/
```

## 说明

- 当前仓库优先围绕 Gmail 场景设计
- 当前示例实现使用了 Apple 生态中的提醒能力
- 规则、模板和接入方式仍在持续迭代

## License

[MIT](./LICENSE)
