import type { Plugin } from "@opencode-ai/plugin"

const server: Plugin = (input) => {
  return Promise.resolve({
    "tool.execute.after": async (ctx, output) => {
      const filePath: string | undefined =
        ctx.args?.file_path ?? ctx.args?.filePath

      if (!filePath || !filePath.endsWith(".json")) return
      if (!filePath.includes("knowledge/articles/")) return
      if (ctx.tool !== "write" && ctx.tool !== "edit") return

      try {
        const result = await input.$`python3 hooks/validate_json.py ${filePath}`.nothrow()
        if (result.exitCode !== 0) {
          output.output += `\n[JSON validation] ${result.stdout.text().trim().split("\n").slice(-5).join("\n")}`
        }
      } catch {
        // Suppress — uncaught exceptions block the agent
      }
    },
  })
}

export default function () {
  return { server }
}
