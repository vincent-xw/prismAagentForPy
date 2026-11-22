// 使用真实 ReadableStream，控制 UTF-8 边界与分块。
export function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
}
export function frame(type: string, data: Record<string, unknown>, id: string | null): string {
  return `${id === null ? '' : `id: ${id}\n`}event: ${type}\ndata: ${JSON.stringify({ type, run_id: 'r1', ...data })}\n\n`
}
