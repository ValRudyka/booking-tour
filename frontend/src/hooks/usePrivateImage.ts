import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { fetchPrivateImage } from '../api/cabinet'

/**
 * An object URL for a private image (a review photo before it is published): an <img src> to the
 * API would carry no token and get a 404, so the file is fetched with the token as a Blob.
 * The URL is freed when the component goes away.
 */
export function usePrivateImage(path: string): string | null {
  const blob = useQuery({
    queryKey: ['private-image', path],
    queryFn: () => fetchPrivateImage(path),
    staleTime: Infinity,
    gcTime: 60_000,
  })
  const url = useMemo(() => (blob.data ? URL.createObjectURL(blob.data) : null), [blob.data])
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url)
  }, [url])
  return url
}
