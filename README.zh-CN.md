<div align="center">

<h1 align="center">CloseOreUI — iOS IPA 修改工具</h1>

<p>修改 Minecraft 基岩版 <code>.ipa</code>，让它不再使用 OreUI、退回经典 JSON-UI ——<br>
做法是把 <code>minecraftpe</code> 里的一个函数改写成 <code>return 0</code>。</p>

<p>
<a href="./README.md">English</a> · <b>中文</b>
</p>

</div>

<br/>

> [!IMPORTANT]
> **输出的 IPA 必须重新签名才能安装。**
> 本工具产出的是**未签名 / ad-hoc 签名**的 IPA，iOS 不会直接接受。
> 你需要用自己的签名方式：Sideloadly、AltStore、ESign、Feather 或 TrollStore。

> [!WARNING]
> **勾选「注入 dylib」后产出的是 ad-hoc 签名包。**
> ad-hoc 签名只在**越狱设备**或 **TrollStore** 下有效。
> 普通（未越狱、无 TrollStore）设备装不上。
> 如果你只是想去掉 OreUI，**不要勾选**这个选项。

## 这个工具做什么

Minecraft 基岩版在绘制新版 OreUI 还是旧版 JSON-UI 之间做选择时，会去查 `minecraftpe`
里的一个屏幕技术栈函数。本工具：

1. 打开 IPA，定位 `Payload/<App>.app/minecraftpe`；
2. **直接解析 ARM64 Mach-O** 找到那个函数 —— 不依赖反汇编器或任何外部 SDK；
3. 把它的函数头改写成 `movz w0, #0` + `ret`，让它永远报告「没有技术栈」；
4. 重新打包 IPA，其余每个条目按字节原样复制。

补丁只有 **8 字节**，原地改写，不会让二进制变大：

```
00 00 80 52    movz w0, #0
C0 03 5F D6    ret
```

除此之外不改任何东西。资源、素材、app bundle 的其余部分都原封不动地拷过去。

## 怎么找到那个函数

两套互相独立的策略，按顺序尝试。这是它能扛住游戏更新、不需要硬编码偏移的原因。

**一、具名注册（优先）**

Minecraft 用字符串键注册它的屏幕技术栈。工具会在二进制里找这些锚点：

```
getTechStackForScreen
vanilla.screenTechStack
```

每命中一个，就顺着字符串交叉引用往下走，展开邻近的分支目标，给每个候选函数打分。
锚点命中会加很重的权重，所以只要锚点还在，基本就是它胜出。

**二、结构指纹（兜底）**

如果锚点没了（改名、被内联、被 strip），就扫描 `LC_FUNCTION_STARTS`，按函数形状打分：

| 特征 | 找什么 |
|---|---|
| 已知函数头 | Minecraft 各版本一直在用的 16 字节 ARM64 函数序言 |
| 返回 | 函数体里有 `ret` |
| 与 1 比较 | `cmp wN, #1` |
| 置 1 / 置 0 | `movz wN, #1` / `movz wN, #0` |
| 条件选择 | 目标为 `w0` 的 `csel` |
| 字段读取 | `ldr xN, [x0, #0x30]`、`ldr wN, [xM, #0x18]` |
| 调用密度 | `bl` 指令数量（会穿透 thunk 解析） |

函数必须**同时**满足：分数过阈值，且比第二名领先一个明确的差距。都不满足时，工具写一份
诊断文件，而不是瞎猜。

**已经改过了？** 能识别 —— 会报告 `state=patched` 并跳过。

## 下载与运行

这个项目**没有安装包，也没有 Release 下载** —— 它就是一个脚本加几个数据文件，所以要
把整个仓库拿下来。

**一、下载仓库**

点绿色的 **Code** 按钮 → **Download ZIP**，解压到任意位置。
（或者克隆：`git clone https://github.com/yinghuajimew/CloseOreUI-iOS-IPA-Patcher.git`）

**二、安装 Python**

需要 Python **3.11 或更高** —— <https://www.python.org/downloads/>。
Windows 上安装时**务必勾选 "Add python.exe to PATH"**，否则下面的命令会提示找不到。

**三、安装唯一的依赖**

在**解压出来的那个文件夹里**（也就是 `main.py` 所在目录）打开终端，执行：

```bash
pip install -r requirements.txt
```

这装的是 `tkinterdnd2`，用来支持拖放。它是可选的 —— 跳过这步程序照样能跑，只是拖放区会
提示你去装，改用「添加文件」按钮即可。

**四、运行**

```bash
python main.py
```

Windows 上如果 `.py` 已关联 Python，双击 `main.py` 也行；但从终端运行更好，出错时能看到
报错信息。

**五、不要把文件夹拆散**

程序是按自己所在目录去找文件的。**不要**把 `main.py` 单独挪出去。这些文件必须和它放在一起：

| 必需文件 | 作用 |
|---|---|
| `lang/*.json` | 界面文本。缺了它，界面上显示的是键名而不是人话。 |
| `HyniSign.dylib`<br>`libhynisloader.dylib`<br>`HyniSwizzleFPS.dylib` | 只在勾选「注入 dylib」时才会读。缺了会让注入报错，**只去 OreUI 的模式不受影响**。 |
| `zsign.exe` | 只用于注入，同上。 |

换句话说：**只想去 OreUI 的话，`main.py` + `lang/` 就够**；但既然要附加功能，就整个仓库都下。

## 环境要求

- Python **3.11+**
- 主要面向 Windows（语言偏好存在注册表 `HKCU\Software\iosoreuipatcher`）。
  macOS / Linux 也能跑，但语言选择不会保存，每次启动都回退到系统语言。
- 可选：`tkinterdnd2`，用于拖放

```bash
pip install -r requirements.txt
```

## 使用步骤

1. 运行 `python main.py`；
2. 拖入一个或多个 `.ipa`，或点「添加文件」；
3. **「注入 dylib」默认不勾** —— 除非你确实要那些附加功能（见下）；
4. 可选：指定输出目录；
5. 点「开始处理」，看下面的日志。

输出命名：

| 模式 | 后缀 | 额外动作 |
|---|---|---|
| 只去 OreUI | `_No_oreui.ipa` | 无 |
| 去 OreUI + 注入 | `_No_oreui_all.ipa` | 注入三个 dylib |

原始 IPA **绝不会**被覆盖。重名时自动加 `_2`、`_3` 等后缀。

源 IPA 旁边会生成两个诊断文件：

- `*_OreUI_v6_result.txt` —— 选中了哪个函数、分数、偏移、改前改后的字节；
- `*_OreUI_v6_diagnostic.txt` —— 只在没找到目标时生成，列出所有考虑过的候选。

反馈失败时请附上这两个文件，里面不含游戏数据，只有偏移。

## 可选的 dylib 注入

> [!NOTE]
> **这三个 dylib 和「去 OreUI」没有任何关系。**
> 去 OreUI 就是上面说的那段纯 Python 二进制补丁，把这三个 dylib 全删了也照样能用。
> 它们是被顺手塞进同一个工具里的、互不相干的附加功能。

勾选「注入 dylib」后，工具会调用 `zsign -a` 把三个 dylib 注入到重打包的 IPA 里。
每一个解决的都是**各自独立**的问题：

### `HyniSign.dylib` —— 修 Xbox 登录

重签名后的 Minecraft 没法把 Xbox Live 设备身份密钥写进 Keychain，因为原来的
Mojang `kSecAttrAccessGroup` 已经和你的签名身份对不上了。于是 `SecKeyCreateRandomKey`
报 **`-34018`（`errSecMissingEntitlement`）**，登录就断了。

这个 dylib 用 `fishhook` 重新绑定 Keychain 相关函数（`SecItemAdd`、`SecItemCopyMatching`、
`SecItemUpdate`、`SecItemDelete`、`SecKeyCreateRandomKey`、`SecKeyGeneratePair`），
在调用真正实现之前把 access group 从查询里剥掉。

**什么时候需要：** 你自己重签了 IPA，然后 Xbox 登录失败。

### `libhynisloader.dylib` —— 从资源包加载完整 `renderer` 文件夹

正常情况下 Minecraft 只从游戏自带的文件里加载渲染器。这个 dylib 钩住 `fopen`，
把请求重定向，让游戏从你的资源包里加载整个 `renderer` 文件夹 ——
思路和安卓上的 Draco Injector 一样。

**什么时候需要：** 你想通过资源包做自定义 RenderDragon 光影或渲染器覆盖。
**什么时候不用管它：** 你只是想去掉 OreUI。

### `HyniSwizzleFPS.dylib` —— 解除 60 帧上限

swizzle `CADisplayLink`，让 ProMotion 的 iPhone / iPad 跑在 60 帧以上，而不是被锁死。

**什么时候需要：** 你的设备有 ProMotion 屏，而游戏感觉被限制了帧率。

### 一览

| 文件 | 解决的问题 | 去 OreUI 需要它吗 |
|---|---|---|
| `HyniSign.dylib` | 重签名后 Xbox 登录报 `-34018` | **不需要** |
| `libhynisloader.dylib` | 自定义渲染器 / 光影加载 | **不需要** |
| `HyniSwizzleFPS.dylib` | 60 帧上限 | **不需要** |

**关于 `libhynisloader.dylib`：** 本仓库这个文件**不是**上游原版。它是一份本地合并编译的
产物，里面同时包含 HynisLoader 的 `fopen` 钩子和 HyniSign 的 `HyniSignCopyStripped`
辅助函数。上游是把这两者分开发布的。

> [!WARNING]
> 因为注入用的是 `zsign -a`（ad-hoc），产出的 `_No_oreui_all.ipa` 只能装在**越狱设备**
> 或通过 **TrollStore** 安装。如果你不属于这两种情况，**别勾这个选项** ——
> 用 `_No_oreui.ipa` 配合你自己的签名工具即可。

## 第三方组件与许可

本项目打包了第三方二进制。它们的许可与署名记录在这里，不写进仓库的 `LICENSE` 文件。

**zsign** —— 以 `zsign.exe` 形式打包。
MIT License，Copyright (c) 2026 zhlynn —— <https://github.com/zhlynn/zsign>

```
MIT License

Copyright (c) 2026 zhlynn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**libhynisloader.dylib** —— 源自 [HynisDev/HynisLoader](https://github.com/HynisDev/HynisLoader)，
该项目为 **GPL-3.0**。分发由它编译出的二进制，意味着本仓库在**该组件上**受 GPL-3.0 约束。

**[HyniSign](https://github.com/vanhoof/HyniSign)** 与 **[HyniSwizzleFPS](https://github.com/vanhoof/HyniSwizzleFPS)** —— 上游仓库**没有提供任何许可文件**。
没有许可即表示作者保留全部权利；这两个二进制是本仓库的实际打包者为了方便用户而附带，
并非基于已核实的授权。如果你是权利人并希望移除，请开 issue。

**fishhook** —— HyniSign 与 HynisLoader 都用到。BSD-3-Clause，
Copyright (c) 2013 Facebook, Inc. —— <https://github.com/facebook/fishhook>

如果你要再分发本项目，请自行核实上述条款。`main.py` 里的去 OreUI 核心逻辑与上述任何一个
第三方项目都没有依赖关系。

## 已知限制

- **仅 iOS，仅 arm64。** 解析器按 AArch64 指令编码实现，32 位构建不适用。
- **输出必须重新签名。** 见顶部提示。
- **`_No_oreui_all.ipa` 需要 TrollStore 或越狱**，因为它是 ad-hoc 签名。
- **游戏大版本更新后结构扫描可能失效。** 届时会生成诊断文件而不是悄悄改错 —— 请把它发出来。
- **不是所有界面都覆盖。** 去 OreUI 影响的是补丁所针对的游戏内 UI 入口，不会改写任何资源文件。
- **面向 Windows。** GUI 把语言偏好写进 Windows 注册表；其它平台回退到系统语言且不保存。

## 鸣谢

- 项目作者：**xiaoli**
- 逆向与补丁思路：**奕帆雨顺**
- 测试与反馈：**xiaoli**、**奕帆雨顺**
- 仓库托管：**樱花祭喵**
- 砸壳调试与适配机会：**银果集团**

第三方项目见上面的「第三方组件与许可」一节。

## 免责声明

本工具用于修改你自己拥有的游戏，仅供个人使用。与 Mojang、微软均无关。
不建议分发改过的包，也不要用于商业用途。
