# Mood Recipes — 产品需求文档（PRD）

| 项目 | 内容 |
| --- | --- |
| 版本 | v2.0（在课程起点项目 `mood-recipes-example` 基础上扩展） |
| 日期 | 2026-10-30 |
| 来源 | 课程作业：用户账号、收藏菜谱、收藏页、自定义心情 |
| 部署形态 | 本地运行：FastAPI + Uvicorn，SQLite 单文件数据库 |
| 界面语言 | 英文（沿用起点项目） |

---

## 1. 背景

起点项目是一个"按心情推荐菜谱"的小网站：用户选一个心情（Happy、Comfort、Energized、Cozy、Adventurous），后端从 TheMealDB 按分类 / 地区随机挑一道菜返回，前端展示图片、配料、做法和视频链接。

起点项目现状（接手时检查发现）：

| 问题 | 影响 |
| --- | --- |
| 文件名错位：`requirements.txt` 里是推荐逻辑代码，`app.py` 里是前端 JS，`recipe_service.py` 里是 FastAPI 主程序 | 项目无法直接运行，依赖清单缺失 |
| 前端有 `Sweet` 心情，后端没有 | 点击后返回 400 |
| 兜底分支调用 `_random_meal_any(client, exclude_ids)`，但函数只接收 1 个参数 | 一旦走到兜底分支就抛 TypeError |
| `login.html` 只有样式，表单不提交，首页也没有入口 | 无登录功能 |

## 2. 目标

1. 用户可以注册、登录、退出、找回密码；密码用 bcrypt 加密存储。
2. 登录用户可以把推荐的菜谱收藏到数据库，每条收藏属于该用户。
3. 新增收藏页 `favorites.html`，展示用户收藏的菜谱和每道菜关联的心情。
4. 用户可以自定义心情（选择 TheMealDB 的分类和地区），推荐逻辑支持这些新心情。
5. 修复起点项目的问题，让项目一条命令就能启动，并有冒烟测试。

### 非目标
- 第三方登录（Google、GitHub）、邮箱验证、多设备会话管理界面
- 自己维护菜谱数据（菜谱始终来自 TheMealDB，本地只存收藏所需的快照）
- 部署上线

## 3. 用户与场景

| 用户 | 场景 |
| --- | --- |
| 访客 | 不登录也能按内置心情找菜谱；想收藏时被引导去登录 |
| 注册用户 | 收藏喜欢的菜，在收藏页按心情筛选、查看做法、取消收藏 |
| 注册用户 | "下雨天想吃热汤"，新建一个 `Rainy Day` 心情，选上 Seafood、British、Irish，以后一键推荐 |
| 忘记密码的用户 | 输入邮箱收到重置链接，设置新密码后重新登录 |

## 4. 功能需求

优先级：**P0** 必须 / **P1** 应该 / **P2** 可选

### 4.1 项目修复（P0）
| 编号 | 需求 |
| --- | --- |
| F-1 | 文件归位，补齐 `requirements.txt`；`uvicorn app:app --reload` 可启动 |
| F-2 | 修复 `Sweet` 心情（映射到 Dessert 等分类），修复兜底函数参数错误 |
| F-3 | 心情列表改为由后端 `/api/moods` 提供，前端不再写死，保证前后端一致 |

### 4.2 用户认证
| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| A-1 | 注册：邮箱 + 密码（≥ 8 位），邮箱唯一且不区分大小写；注册成功自动登录 | P0 |
| A-2 | 登录：邮箱 + 密码；错误时统一提示"邮箱或密码不正确"，不泄露邮箱是否存在 | P0 |
| A-3 | 密码使用 bcrypt 哈希（cost 12），数据库不存明文 | P0 |
| A-4 | 会话：服务端会话表 + httpOnly、SameSite=Lax 的 cookie；数据库只存令牌的 SHA-256 哈希；退出时删除会话 | P0 |
| A-5 | 忘记密码：输入邮箱 → 生成一次性重置令牌（30 分钟有效，只存哈希）→ 发送重置链接；无论邮箱是否存在都返回同样提示 | P0 |
| A-6 | 邮件发送：配置了 SMTP 就用 SMTP 发；未配置时把链接打印到服务器控制台，方便本地演示 | P0 |
| A-7 | 重置密码页：设置新密码后令牌作废，该用户所有旧会话失效 | P0 |
| A-8 | 登录页以课程提供的 `login.html` 设计为基础（紫色渐变、玻璃卡片、下划线输入框），在同一卡片内切换 Login / Register / Forgot Password | P0 |
| A-9 | Remember Me：勾选时会话 30 天，不勾选为浏览器会话 cookie（服务端 1 天过期） | P1 |
| A-10 | 显示 / 隐藏密码按钮；注册时显示密码要求 | P1 |
| A-11 | 登录失败限流：同一邮箱 15 分钟内失败 10 次后暂时拒绝 | P2 |

### 4.3 收藏菜谱
| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| S-1 | 推荐卡片上有"收藏"按钮；未登录时点击跳转登录页，登录后回到首页 | P0 |
| S-2 | 收藏写入数据库（SQLAlchemy 2.0 异步 + aiosqlite），关联当前用户；同一用户同一道菜只存一条 | P0 |
| S-3 | 保存菜谱快照（名称、图片、分类、地区），收藏页不需要逐条请求 TheMealDB | P0 |
| S-4 | 记录收藏时所选的心情；同一道菜在另一个心情下再次收藏时，追加这个心情标签 | P0 |
| S-5 | 已收藏的菜，按钮显示为"已收藏"，再点一次取消收藏 | P1 |

### 4.4 收藏页 `favorites.html`
| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| V-1 | 未登录访问时跳转登录页 | P0 |
| V-2 | 卡片网格：图片、菜名、分类 / 地区、关联的心情标签、收藏时间 | P0 |
| V-3 | 取消收藏 | P0 |
| V-4 | 空状态：说明如何收藏，并提供返回首页的按钮 | P0 |
| V-5 | 按心情筛选（显示每个心情的收藏数） | P1 |
| V-6 | 点击卡片打开详情弹层：配料、做法、视频链接（详情实时从 TheMealDB 取） | P1 |

### 4.5 自定义心情
| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| M-1 | 登录用户点击 `+ New mood`，填写名称、可选 emoji，并从 TheMealDB 的分类和地区列表中多选（至少选 1 项） | P0 |
| M-2 | 自定义心情只对创建者可见，和内置心情一起出现在心情列表里 | P0 |
| M-3 | 推荐逻辑：内置心情和自定义心情走同一套"按分类 / 地区取菜、去重、排除已看过的菜"的流程 | P0 |
| M-4 | 名称校验：1–24 个字符；同一用户下不能与已有心情（含内置）重名 | P0 |
| M-5 | 删除自定义心情；已收藏菜谱上的该心情标签同时移除，收藏本身保留 | P1 |
| M-6 | 分类 / 地区列表由后端缓存（1 小时），减少对 TheMealDB 的请求 | P1 |

### 4.6 质量
| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| Q-1 | pytest 冒烟测试：首页、注册、登录、退出、`/me`、忘记 / 重置密码、收藏增删查、用户隔离、自定义心情及其推荐；TheMealDB 用假数据替代，测试不联网 | P0 |
| Q-2 | README：安装、启动、SMTP 配置、接口说明 | P0 |
| Q-3 | 统一的错误响应格式 `{ "detail": "..." }`，前端显示友好提示 | P1 |

## 5. 页面与交互

| 页面 | 内容 |
| --- | --- |
| `index.html` | 顶栏：未登录显示 `Log in` / `Register`；已登录显示邮箱、`Favorites`、`Log out`。心情按钮（内置 + 自定义 + `+ New mood`）。推荐卡片增加收藏按钮 |
| `login.html` | 沿用提供的设计。三种视图：Login（Remember Me、Forget Password、Register 链接）、Register、Forgot Password。成功后跳回 `?next=` 指定的页面 |
| `reset-password.html` | 同一视觉风格；输入两次新密码；成功后跳转登录 |
| `favorites.html` | 顶栏与首页一致；心情筛选条；收藏卡片网格；详情弹层 |

## 6. 技术方案

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI + Uvicorn |
| 数据库 | SQLite（`mood_recipes.db`），SQLAlchemy 2.0 异步 ORM + aiosqlite |
| 密码 | bcrypt |
| 会话 | 随机令牌（`secrets.token_urlsafe`）放在 httpOnly cookie，数据库存 SHA-256 |
| 邮件 | 标准库 `smtplib`（在线程中执行，不阻塞事件循环），未配置时输出到控制台 |
| 配置 | 环境变量 / `.env`（`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM`、`APP_BASE_URL`、`DATABASE_URL`） |
| 前端 | 静态 HTML + Tailwind（CDN，沿用起点项目）+ 原生 JS |
| 菜谱数据 | TheMealDB 免费接口（httpx 异步请求） |
| 测试 | pytest + FastAPI TestClient，TheMealDB 用假客户端替代 |

### 6.1 数据模型
```
users            id, email (唯一, 小写), password_hash, created_at
sessions         id, user_id → users, token_hash (唯一), expires_at, created_at
password_resets  id, user_id → users, token_hash (唯一), expires_at, used_at
moods            id, user_id → users (内置心情为空), slug, label, emoji,
                 categories (JSON), areas (JSON), created_at
                 唯一约束 (user_id, slug)
favorites        id, user_id → users, meal_id, name, image, category, area, created_at
                 唯一约束 (user_id, meal_id)
favorite_moods   favorite_id → favorites, mood_id → moods   （多对多：一道菜可以有多个心情）
```
内置心情在启动时写入 `moods` 表（`user_id` 为空），这样内置心情和自定义心情使用同一套推荐逻辑。

### 6.2 接口
| 方法 | 路径 | 说明 | 登录 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 注册并登录 | — |
| POST | `/api/auth/login` | 登录（`remember` 可选） | — |
| POST | `/api/auth/logout` | 退出 | — |
| GET | `/api/auth/me` | 当前用户 | ✅ |
| POST | `/api/auth/forgot-password` | 发送重置链接 | — |
| POST | `/api/auth/reset-password` | 用令牌设置新密码 | — |
| GET | `/api/moods` | 内置心情 +（登录时）我的心情 | — |
| POST | `/api/moods` | 新建心情 | ✅ |
| DELETE | `/api/moods/{id}` | 删除自己的心情 | ✅ |
| GET | `/api/meal-filters` | TheMealDB 分类与地区列表 | — |
| GET | `/api/recipe?mood=&exclude=` | 按心情推荐 | 自定义心情需登录 |
| GET | `/api/recipes/{meal_id}` | 菜谱详情 | — |
| GET | `/api/favorites` | 我的收藏（含心情） | ✅ |
| POST | `/api/favorites` | 收藏 `{meal_id, mood}` | ✅ |
| DELETE | `/api/favorites/{id}` | 取消收藏 | ✅ |

## 7. 安全要求
- 密码只存 bcrypt 哈希；会话令牌、重置令牌只存 SHA-256 哈希。
- cookie：`HttpOnly`、`SameSite=Lax`、`Path=/`；通过 https 访问时加 `Secure`。
- 所有收藏、心情的查询都带 `user_id` 条件，用户之间互相不可见、不可删除。
- 登录、忘记密码不泄露邮箱是否注册。
- 写操作只接受 JSON 请求体，配合 SameSite cookie 防止跨站表单提交。

## 8. 验收标准
1. 全新环境按 README 安装后，`uvicorn app:app --reload` 启动，首页可推荐菜谱，6 个内置心情都能用。
2. 注册 → 退出 → 登录 → 刷新后仍保持登录；数据库中看不到明文密码。
3. 忘记密码：控制台（或邮箱）收到链接，重置后旧密码失效、新密码可登录，链接不能重复使用。
4. 登录后收藏菜谱，收藏页显示该菜谱及其心情；另一个账号看不到。
5. 新建自定义心情后立刻出现在首页，并能推荐出匹配分类 / 地区的菜。
6. `pytest` 全部通过，且测试不依赖网络。

## 9. 里程碑
| 阶段 | 内容 |
| --- | --- |
| M1 修复 | F-1 ~ F-3 |
| M2 账号 | A-1 ~ A-8 |
| M3 收藏 | S-1 ~ S-4、V-1 ~ V-4 |
| M4 心情 | M-1 ~ M-4 |
| M5 测试与文档 | Q-1、Q-2 |
| M6 P1 | A-9、A-10、S-5、V-5、V-6、M-5、M-6、Q-3 |
| M7 发布 | 推送到 GitHub 公开仓库 |

## 10. 完成情况（2026-10-30）
| 范围 | 状态 | 验证 |
| --- | --- | --- |
| F-1 ~ F-3 修复 | ✅ | 文件归位、补齐依赖；Sweet 心情可用；兜底分支改为 `MealDB.random_meal()`；心情列表来自 `/api/moods` |
| A-1 ~ A-8 账号（P0） | ✅ | pytest：注册、登录、退出、`/me`、bcrypt 哈希入库、会话令牌只存哈希、登录错误不泄露账号、忘记 / 重置密码、旧会话失效、链接不可复用 |
| S-1 ~ S-4、V-1 ~ V-4 收藏（P0） | ✅ | pytest：收藏增删查、同一道菜多心情标签、用户隔离；浏览器：未登录点收藏 → 注册 → 回到首页自动收藏 |
| M-1 ~ M-4 心情（P0） | ✅ | pytest：新建、校验、重名、他人不可见、推荐只返回所选分类 / 地区；浏览器：新建 Rainy Day 并推荐出 Irish 菜 |
| Q-1、Q-2 | ✅ | 27 项 pytest（假 TheMealDB，不联网）；README |
| P1：A-9、A-10、S-5、V-5、V-6、M-5、M-6、Q-3 | ✅ | Remember Me 持久 cookie、显示密码、取消收藏、按心情筛选、详情弹层、删除心情保留收藏、分类 / 筛选结果缓存 1 小时、统一错误文案 |
| P2：A-11 登录限流 | ✅ | 同一邮箱 15 分钟内失败 10 次返回 429 |
