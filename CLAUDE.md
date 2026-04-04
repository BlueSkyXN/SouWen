## 收尾追问规则
完成任务准备结束之前，必须采用以下提问策略：

1. 若当前环境存在可用的用户提问工具且未被禁用，优先使用工具提问（例如 `ask_user`、`AskUserQuestion`、`request_user_input`）
2. 若无可用提问工具，则回退为普通文本提问

提问内容使用固定收尾话术：

`还有没有补充要做的事情？请一次性列出，我将继续在本轮内处理。`

原则上未经用户明确同意结束任务，才能结束本轮，否则继续追问直到用户明确结束。

### ask_user 工具使用规范

调用 `ask_user` 时，`requestedSchema` 参数必须是合法 JSON 对象，需要注意以下几点避免失败：

1. **字符串值必须用 Unicode 转义处理中文引号和特殊字符**：description/title 中不要直接嵌入中文引号（如 `""`）等可能干扰 JSON 解析的字符，改用 `\uXXXX` 转义或简化表述。(不影响正常中文描述的表达，只需要避免引号等特殊字符导致 JSON 解析失败)
2. **保持 schema 简洁**：只用必要字段（`type`, `title`, `description`），避免冗长嵌套。
3. **正确示例**：
```json
{"properties": {"todo": {"type": "string", "title": "xxxx", "description": "xxxx"}}, "required": ["todo"]}
```
4. **错误示例**：在 description 中直接写 `输入"无"即可` 会因为中文引号干扰 JSON 解析，导致 `Expected object, received string` 错误。
5. **可选字段类型**：`string`（自由文本）、`boolean`（是/否）、带 `enum` 的 `string`（下拉选择）、`number`/`integer`（数字）。
