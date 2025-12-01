# RedNote (小红书) Crawler Plugin

这是一个基于 Crawl4AI 框架的 RedNote (小红书) 爬虫插件，使用 Playwright 浏览器自动化进行数据抓取。

## 功能特性

- ✅ 使用 Playwright 浏览器模式进行真实点击交互
- ✅ 自动检测验证码/人机验证
- ✅ 支持通过 WebHook 推送验证信息到飞书
- ✅ 支持移动端 H5 手动验证
- ✅ 自动登录检测和等待
- ✅ 搜索关键词并逐个点击笔记
- ✅ 抽取图片列表、文本信息、评论信息

## 安装要求

确保已安装以下依赖：

```bash
pip install crawl4ai playwright aiohttp
playwright install chromium
```

## 使用方法

### 基本使用

```python
import asyncio
from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler

async def main():
    # 创建爬虫实例
    crawler = RedNoteCrawler(
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url"
    )
    
    # 运行爬虫
    result = await crawler.run(
        search_keyword="牛奶",
        max_notes=10,
        headless=False  # 非无头模式，方便手动操作
    )
    
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 通过 CrawlerHub 使用

```python
import asyncio
from crawl4ai import CrawlerHub

async def main():
    # 获取 RedNote 爬虫
    RedNoteCrawler = CrawlerHub.get("rednote")
    
    if RedNoteCrawler:
        crawler = RedNoteCrawler(
            feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url"
        )
        
        result = await crawler.run(
            search_keyword="牛奶",
            max_notes=10
        )
        
        print(result)
    else:
        print("RedNote crawler not found")

if __name__ == "__main__":
    asyncio.run(main())
```

## 参数说明

### RedNoteCrawler 初始化参数

- `feishu_webhook_url` (str, optional): 飞书 WebHook URL，用于接收验证码通知

### run() 方法参数

- `url` (str, optional): 起始 URL，默认为 RedNote 首页
- `search_keyword` (str): 搜索关键词，默认为 "牛奶"
- `max_notes` (int): 最大爬取笔记数量，默认为 10
- `feishu_webhook_url` (str, optional): 飞书 WebHook URL（如果初始化时未设置）
- `headless` (bool): 是否使用无头模式，默认为 False（建议 False，方便手动操作）
- `verbose` (bool): 是否显示详细日志，默认为 True
- `browser_type` (str): 浏览器类型，默认为 "chromium"

## 返回数据格式

```json
{
  "success": true,
  "total_notes": 10,
  "notes": [
    {
      "url": "https://www.xiaohongshu.com/explore/...",
      "images": [
        "https://sns-img-xxx.xhscdn.com/...",
        "https://sns-img-xxx.xhscdn.com/..."
      ],
      "text": "笔记的文本内容...",
      "comments": [
        {
          "text": "评论内容",
          "author": "用户名",
          "likes": 10
        }
      ]
    }
  ],
  "error": null
}
```

## 验证码处理流程

1. 插件自动检测页面上的验证码/人机验证
2. 检测到验证码后，自动发送通知到飞书
3. 飞书通知包含：
   - 当前页面 URL
   - 移动端 H5 验证链接
   - 操作步骤说明
4. 用户在移动端完成验证
5. 插件自动检测验证完成并继续爬取

## 注意事项

1. **浏览器模式**: 建议使用非无头模式 (`headless=False`)，以便手动完成登录和验证
2. **登录**: 首次使用时需要在浏览器中手动登录 RedNote 账号
3. **验证码**: 如果遇到验证码，插件会暂停并等待用户在移动端完成验证
4. **选择器**: RedNote 的页面结构可能会变化，如果选择器失效，需要更新代码中的选择器
5. **速率限制**: 建议设置合理的 `max_notes` 和添加延迟，避免触发反爬虫机制

## 飞书 WebHook 配置

1. 在飞书群组中添加自定义机器人
2. 获取 WebHook URL
3. 将 URL 传递给爬虫的 `feishu_webhook_url` 参数

## 故障排除

### 无法找到笔记元素

如果无法找到笔记元素，可能需要更新选择器。检查 RedNote 页面的实际 HTML 结构，更新 `crawler.py` 中的选择器。

### 验证码检测失败

验证码检测依赖于页面上的特定元素和文本。如果 RedNote 更新了验证码样式，可能需要更新 `_detect_captcha` 方法中的检测逻辑。

### 页面加载超时

如果页面加载较慢，可以增加超时时间或检查网络连接。

## 开发说明

这是一个独立的插件，位于 `crawl4ai/crawlers/rednote/` 目录下，不依赖 Crawl4AI 主体代码的修改。

插件遵循 Crawl4AI 的插件规范：
- 继承 `BaseCrawler` 类
- 实现 `async run()` 方法
- 定义 `__meta__` 元数据

