import { describe, it, expectTypeOf } from 'vitest'
import type { PaginatedResponse, AuditFields, ApiError } from '../api'

describe('API types', () => {
  it('PaginatedResponse has correct shape', () => {
    const response: PaginatedResponse<{ id: number; name: string }> = {
      count: 10,
      next: 'http://example.com/api/v1/items/?page=2',
      previous: null,
      results: [{ id: 1, name: 'Test' }],
    }

    expectTypeOf(response.count).toBeNumber()
    expectTypeOf(response.next).toEqualTypeOf<string | null>()
    expectTypeOf(response.results).toBeArray()
    expectTypeOf(response.results[0]).toHaveProperty('id')
  })

  it('AuditFields has correct shape', () => {
    const audit: AuditFields = {
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 1,
      updated_by: null,
    }

    expectTypeOf(audit.created_at).toBeString()
    expectTypeOf(audit.created_by).toEqualTypeOf<number | null>()
  })

  it('ApiError has required error field', () => {
    const error: ApiError = {
      error: 'Something went wrong',
    }

    expectTypeOf(error.error).toBeString()
    expectTypeOf(error).toHaveProperty('detail')
  })
})
