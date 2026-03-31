'use client'

import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs'

interface PayloadTabsProps {
  prompt: string | null
  response: string | null
  rawResponse: string | null
}

function PayloadBlock({ content }: { content: string | null }) {
  if (content === null || content === '') {
    return (
      <p className="text-sm text-zinc-400 dark:text-zinc-500 italic">
        No content available
      </p>
    )
  }
  return (
    <pre className="overflow-auto rounded-md bg-zinc-50 p-3 font-mono text-xs text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 max-h-72 whitespace-pre-wrap break-words">
      {content}
    </pre>
  )
}

export function PayloadTabs({ prompt, response, rawResponse }: PayloadTabsProps) {
  return (
    <Tabs defaultValue="prompt">
      <TabsList>
        <TabsTrigger value="prompt">Prompt</TabsTrigger>
        <TabsTrigger value="response">Response</TabsTrigger>
        <TabsTrigger value="raw">Raw Response</TabsTrigger>
      </TabsList>
      <TabsContent value="prompt" className="mt-2">
        <PayloadBlock content={prompt} />
      </TabsContent>
      <TabsContent value="response" className="mt-2">
        <PayloadBlock content={response} />
      </TabsContent>
      <TabsContent value="raw" className="mt-2">
        <PayloadBlock content={rawResponse} />
      </TabsContent>
    </Tabs>
  )
}
