# souwen-example-plugin — 最小示例插件

演示如何为 SouWen 编写外部插件。此插件仅回显 URL，不依赖任何第三方服务。

## 安装

```bash
cd examples/minimal-plugin
pip install -e .
```

## 验证

```bash
python -c "from souwen.registry import all_adapters; print([n for n in all_adapters() if 'example' in n])"
```

## 结构

```
souwen_example_plugin/
├── __init__.py      # 声明 SourceAdapter (entry point)
├── client.py        # 实现 Client 合约
└── handler.py       # 可选：注册 fetch handler
```

## 对接规范

完整规范见 SouWen 文档：[plugin-integration-spec.md](../../docs/plugin-integration-spec.md)
