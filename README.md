# ShotFrame · 截图加框

一键给截图加上「应用窗口卡片」包装，让读者在图文里一眼认出这是截图，不再和正文糊在一起。

给公众号、知乎、掘金、博客写图文的作者设计。离线运行，图片不出你的电脑。

| 处理前 | 处理后 |
|---|---|
| ![before](assets/demo-before.png) | ![after](assets/demo-after.png) |

## 它解决什么问题

截图大多是白底黑字，贴进文章里和正文抢在一起，读者分不清哪是图哪是文。ShotFrame 给截图加上灰底衬托、白色圆角窗口、标题栏圆点、小标签和阴影描边，截图内容 100% 原样保留，只加包装。

## 三个特点

- **拖进来就完事**：图片、整个文件夹、甚至整篇 docx 文稿，拖进窗口一键全处理
- **docx 整篇处理**：写完的稿子不用一张张抠图重贴，直接把 .docx 拖进来，所有插图加框并自动修正显示比例，输出「原名-加框.docx」，原文件不动
- **离线 + 开源**：本地运行不上传，MIT 协议，代码就这几百行，欢迎自己改样式

## 下载使用

到 [Releases](../../releases) 下载 `ShotFrame.exe`，双击打开，把图拖进去。

可配置项，标签文字（默认「实测截图」，可清空）、底色（浅灰/浅紫/浅蓝/浅绿）、窗口圆点开关。小于 200×100 的小图（表情、图标）会自动跳过。

## 命令行用法

```bash
ShotFrame.exe 截图.png 另一张.jpg --label "实测截图"
ShotFrame.exe 截图文件夹 --preset purple --recursive
ShotFrame.exe 我的稿子.docx
ShotFrame.exe 图.png --no-dots --no-label --out D:\输出目录
```

注意，exe 是无控制台窗口的打包，命令行输出在部分终端里看不到；重度命令行用户建议直接跑源码 `python main.py ...`。

## 从源码运行

```bash
pip install pillow python-docx tkinterdnd2
python main.py            # 打开图形界面
python main.py 图.png     # 命令行模式
```

## 自己打包 exe

```bash
pip install pyinstaller
build.bat
```

## 常见问题

**Windows Defender 报毒？** PyInstaller 打包的单文件 exe 存在误报概率，这是打包方式的通病，不是程序有问题。介意的话请直接用源码运行，或自行打包。

**docx 里有的图没处理？** 矢量图（emf/wmf/svg）、动图（gif）和小于 200×100 的图会跳过，处理日志里会写明。

**图片会变形吗？** 不会。docx 模式下每张图的显示高度会按新宽高比重新计算，宽度保持不变。

## 原理

一张卡片 = 底色画布 + 投影 + 白色圆角窗口（标题栏 + 三个圆点 + 标签文字）+ 截图本体 + 描边。核心代码在 `shotframe/core.py` 的 `frame_image()`，docx 处理在 `shotframe/docx_frame.py`，改样式只需要动 `FrameStyle`。

## License

[MIT](LICENSE)，作者 [笃行其道](https://github.com/)。这个工具诞生于一次公众号排版，如果它帮到了你，欢迎点个 star。
