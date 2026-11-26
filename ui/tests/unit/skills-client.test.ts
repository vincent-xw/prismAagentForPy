import { expect, test, vi } from 'vitest'

import { createCoreClient } from '@/lib/api/client'
import { skillDetailSchema, skillsSchema } from '@/lib/api/contracts'
import { runDto } from '../support/fixtures'

function fakeFetch(payload: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

test('listSkills 严格解析', async () => {
  const fetcher = fakeFetch({
    items: [{ name: 'pdf', description: 'd', path: '/a', root: '/', shadowed: false }],
  })
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => null, fetcher })

  await expect(client.listSkills()).resolves.toMatchObject({ items: [{ name: 'pdf' }] })
})

test('createRun 携带 skill_name', async () => {
  const fetcher = fakeFetch(runDto())
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => null, fetcher })

  await client.createRun('s1', { input: 'hi', skill_name: 'pdf-tools' })

  const body = JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))
  expect(body).toEqual({ input: 'hi', skill_name: 'pdf-tools' })
})

test('skills schema rejects unknown shape', () => {
  expect(() => skillsSchema.parse({ items: [{ name: 'x' }] })).toThrow()
  expect(() =>
    skillDetailSchema.parse({ name: 'x', description: 'd', content: 'c', resources: [] }),
  ).not.toThrow()
})
