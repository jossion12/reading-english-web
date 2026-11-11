# Reading-DB-Supabase Supabase数据底座
## 1. 概述
### 定位
共享存储底座，基于Postgres，使用Supabase托管；负责持久化素材记录、阅读文章；配置RLS行级安全策略做权限隔离。
### 依赖
Supabase免费实例
### 目标
稳定存储业务数据，严格隔离读写权限；支持前端筛选、日期查询；学生前端仅有只读权限，无法修改数据。

## 2. 数据表结构
### 表1：source_log（素材梗概表）
| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | uuid | 主键 |
| source_fingerprint | text | SHA256梗概指纹，唯一索引 |
| source_summary | text | 标准化素材梗概全文 |
| create_at | timestamp with time zone | 创建时间 |
| remark | text | 备注：来源链接、备注说明 |

### 表2：articles（阅读文章表）
| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | uuid | 主键 |
| publish_date | date | 发布日期，日历查询使用 |
| title_en | text | 英文标题 |
| title_cn | text | 中文标题 |
| level | text | 难度 L1 / L2 / L3 |
| theme | text | 主题大类 |
| sub_theme | text | 子话题 |
| style | text | 文体 |
| color_tag | text | 标签颜色色值 #xxxxxx |
| english_paras | jsonb | 英文段落数组 |
| chinese_paras | jsonb | 中文段落数组 |
| sort | int | 同一天文章排序序号 |
| is_published | boolean | 是否对外展示 |
| source_id | uuid | 外键关联 source_log.id，常青素材可为null |

## 3. 索引配置
1. source_log：`source_fingerprint` UNIQUE索引
2. articles：
   - publish_date 索引（日历按日期查询）
   - theme, level, style 复合索引（筛选加速）

## 4. RLS 行级安全策略
### source_log
- anon匿名角色：禁止 SELECT / INSERT / UPDATE / DELETE
- 管理员登录角色：允许 SELECT / INSERT / UPDATE / DELETE

### articles
- anon匿名角色：仅允许 SELECT，禁止增删改
- 管理员登录角色：允许 SELECT / INSERT / UPDATE / DELETE

## 5. 约束
- 外键约束：articles.source_id 引用 source_log.id，支持 SET NULL
- is_published=false 的文章，前端查询默认过滤不展示

## 6. 边界说明（不做）
- ❌ 不包含业务代码、接口逻辑，仅存储与权限控制
- ❌ 收藏、阅读打卡状态存储在浏览器localStorage，不在数据库中保存
