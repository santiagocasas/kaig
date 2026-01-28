SELECT
    best_chunk_score,
    summary,
    doc.{id, filename, content_type},
    array::transpose([
        contents,
        scores,
        chunks,
        chunk_indexes
    ]).map(|$arr| {
        content: $arr[0],
        score: $arr[1],
        id: $arr[2],
        chunk_index: $arr[3]
    }) AS chunks
FROM (
    SELECT
        doc,
        summary,
        math::max(score) AS best_chunk_score,
        array::group(content) AS contents,
        array::group(score) AS scores,
        array::group(id) AS chunks,
        array::group(index) AS chunk_indexes
        FROM (
            SELECT *,
                1.0 AS score
                OMIT embedding
            FROM chunk
            WHERE string::contains(
                string::lowercase(content),
                string::lowercase($query)
            )
            LIMIT 50
        )
        GROUP BY doc
        ORDER BY best_chunk_score DESC
);
