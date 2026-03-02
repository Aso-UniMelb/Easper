"""
Segments cleanup
(c) 2026 
"""
def segments_cleanup(init_segments, min_segment=0.5, min_silence=0.5):
    """
    Cleans up segments by merging close and removing overlapping and very short segments.
    
    Args:
        init_segments: List of (start_time, end_time, speaker_id) tuples
        min_segment: Minimum segment duration
        min_silence: Minimum silence duration between segments
    
    Returns:
        List of (start_time, end_time, speaker_id) tupless
    """
    from collections import defaultdict
    # split longer than 30 seconds into 30 seconds segments
    for seg in init_segments:
        if seg[1] - seg[0] > 30.0:
            init_segments.remove(seg)
            while seg[1] - seg[0] > 30.0:
                init_segments.append((seg[0], seg[0] + 30.0, seg[2]))
                seg = (seg[0] + 30.0, seg[1], seg[2])

    segregated = defaultdict(list)
    for seg in init_segments:
        segregated[seg[2]].append(seg)

    clean1 = []
    for sp, sp_segments in segregated.items():
        sp_segments.sort(key=lambda x: x[0])
        # Joins up same speaker segments
        cleaned = [sp_segments[0]]
        for i in range(1, len(sp_segments)):
            start = sp_segments[i][0]
            end = sp_segments[i][1]
            label = sp_segments[i][2]
            if start - cleaned[-1][1] < min_silence:
                if end - cleaned[-1][0] < 30.0:
                    # merge close and overlapping segments
                    cleaned[-1] = (cleaned[-1][0], end, label)
                else:
                    # temporary add
                    cleaned.append((start, end, label))
            else:
                # check if the previous segment is short
                if cleaned[-1][1] - cleaned[-1][0] < min_segment:
                    cleaned[-1] = ((start, end, label))
                else:
                    cleaned.append((start, end, label))
        clean1.extend(cleaned)

    # delete segments shorter than min_segment
    clean1 = [seg for seg in clean1 if seg[1] - seg[0] >= min_segment]

    # check for complete overlap
    clean2 = clean1
    for seg in clean1:
        filtered = [item for item in clean2 if (item[1] < seg[1] and item[0] > seg[0])]
        if filtered:
            for item in filtered:
                clean2.remove(item)
    # handle partial overlaps
    clean3 = sorted(clean2, key=lambda x: x[0])
    cleaned = [clean3[0]]
    for i in range(1, len(clean3)):
        start = clean3[i][0]
        end = clean3[i][1]
        label = clean3[i][2]
        if start <= cleaned[-1][1]:
            # Resolve by setting new start to midpoint
            # And setting last segment end to midpoint
            overlap = cleaned[-1][1] - start
            midpoint = start + overlap // 2
            # update previous segment end
            if midpoint - cleaned[-1][0] < min_segment:
                # delete the previous segment if it is too short
                cleaned[-1] = (start, end, label)
            else:
                cleaned[-1] = (cleaned[-1][0], midpoint, cleaned[-1][2])
                # do not add if the new segment is too short
                if end - midpoint > min_segment:
                    cleaned.append( (midpoint, end, label) )
        else:
            cleaned.append((start, end, label))
    return cleaned