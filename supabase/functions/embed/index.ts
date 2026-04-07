import 'jsr:@supabase/functions-js/edge-runtime.d.ts'

const model = new Supabase.ai.Session('gte-small')

Deno.serve(async (req: Request) => {
  try {
    const { input } = await req.json()

    if (!input) {
      return new Response(
        JSON.stringify({ error: 'input is required' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      )
    }

    // Handle array of texts
    if (Array.isArray(input)) {
      const embeddings = []
      for (const text of input) {
        const output = await model.run(text, { mean_pool: true, normalize: true })
        embeddings.push(Array.from(output))
      }
      return new Response(
        JSON.stringify({ embeddings }),
        { headers: { 'Content-Type': 'application/json' } }
      )
    }

    // Handle single text
    const output = await model.run(input, { mean_pool: true, normalize: true })
    return new Response(
      JSON.stringify({ embedding: Array.from(output) }),
      { headers: { 'Content-Type': 'application/json' } }
    )
  } catch (err) {
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    )
  }
})