# AGENT.md v4 — HCMC AI Challenge 2026 Competition Context Only

## 0. Purpose

This document is a **competition-context source of truth** for the **Ho Chi Minh City AI Challenge 2026**.

It is intended to be loaded into a coding/design agent so that the agent can understand:

- the competition constraints
- the official theme
- the problem statement
- expected task/query types
- expected input/output behavior
- competition rounds
- known and unknown requirements
- sample queries

This document intentionally **does not include**:

- system architecture
- technical implementation strategy
- product design
- model recommendations
- tech stack
- engineering roadmap
- evaluation framework
- optimization strategy

A separate agent or later prompt should use this context to propose system design.

---

## 1. Competition Identity

### Official Vietnamese Name

**Hội thi Thử thách Trí tuệ Nhân tạo Thành phố Hồ Chí Minh năm 2026**

### English Name

**Ho Chi Minh City Artificial Intelligence Challenge 2026**

Common short name:

**AI Challenge 2026**

### Official Portal

`https://aichallenge.hochiminhcity.gov.vn/`

---

## 2. Organizers and Coordinating Units

### Lead Organizer

- **Ho Chi Minh City Department of Science and Technology**
- Vietnamese: **Sở Khoa học và Công nghệ TP.HCM**
- Abbreviation: **Sở KHCN**

### Coordinating Units

- **Vietnam National University, Ho Chi Minh City**
  - Vietnamese: **Đại học Quốc gia TP.HCM**
  - Abbreviation: **ĐHQG-HCM**

- **Ho Chi Minh City Department of Education and Training**
  - Vietnamese: **Sở Giáo dục và Đào tạo TP.HCM**
  - Abbreviation: **Sở GDĐT**

- **Ho Chi Minh Communist Youth Union of Ho Chi Minh City**
  - Vietnamese: **Thành Đoàn TP.HCM**

- **Ho Chi Minh City Computer Association**
  - Vietnamese: **Hội Tin học TP.HCM**
  - Abbreviation: **HCA**

---

## 3. Competition Goals

The competition aims to:

1. Promote learning in informatics and artificial intelligence.
2. Encourage AI research and applications that contribute to Ho Chi Minh City becoming a smart city.
3. Encourage individuals and research groups in Vietnam and internationally to propose and improve advanced AI solutions for important real-life problems.
4. Promote and spread creative science and technology solutions using AI.
5. Attract attention from individuals and research groups to practical problems originating from Ho Chi Minh City.
6. Support solutions that may be applied more broadly across Vietnam and potentially at regional/international levels.

These goals are background context only. They are not direct technical requirements unless later specified by the organizers.

---

## 4. Participant Eligibility

### Eligible Participants

The competition is open to:

- Vietnamese citizens
- Overseas Vietnamese
- Foreign nationals
- Individuals
- Teams

### Registration Format

Participants may register:

- individually
- as a team

### Team Size Constraint

Each team may have:

- **maximum 5 members**

This is an official constraint.

---

## 5. Competition Divisions

The competition has **2 divisions**.

### Division A

For:

- university students
- youth participants
- people interested in information technology and artificial intelligence

Vietnamese description:

> Sinh viên, thanh niên có quan tâm đến lĩnh vực công nghệ thông tin, trí tuệ nhân tạo.

### Division B

For:

- high school students
- students interested in information technology
- students who want to learn about artificial intelligence

Vietnamese description:

> Học sinh các trường trung học phổ thông yêu thích công nghệ thông tin và muốn tìm hiểu về trí tuệ nhân tạo.

### Special Note for Division B

Division B participants are allowed to use tools provided by the organizers to complete competition requirements.

Vietnamese source meaning:

> Đối với thí sinh bảng B (học sinh THPT) được phép sử dụng công cụ có sẵn do Ban tổ chức cung cấp để thực hiện các yêu cầu của cuộc thi đưa ra.

This does not necessarily apply to Division A.

---

## 6. Registration

### Registration Channel

Participants register through the official electronic portal:

`https://aichallenge.hochiminhcity.gov.vn/`

### Registration Period

Expected registration period:

- from the official competition launch date
- until **June 15, 2026**

---

## 7. Official Timeline

The schedule below is based on official information currently available.

| Event | Expected Time |
|---|---|
| Competition launch | May 15–20, 2026 |
| Registration deadline | June 15, 2026 |
| Announcement of preliminary round content and requirements | June 25, 2026 |
| Participant training sessions | June–July 2026 |
| Preliminary round | August 2026 |
| Announcement of preliminary results | August 30, 2026 |
| Final round | September 12–26, 2026 |
| Award ceremony / closing ceremony | October 2026 |

### Timeline Caveat

The organizers may adjust the schedule depending on actual conditions.

Vietnamese source meaning:

> Theo tình hình thực tế, Ban tổ chức sẽ có thay đổi và thông báo sau.

---

## 8. Official 2026 Theme

### English Theme

**Intelligent virtual Assistant for advanced Analysis and Information retrieval from large-scale Multimedia data**

### Vietnamese Theme / Problem Statement

> Trợ lý ảo thông minh hỗ trợ phân tích và truy xuất thông tin chuyên sâu trong dữ liệu lớn multimedia.

### Data Modalities Mentioned Officially

The official description explicitly mentions multimedia data including:

- images
- audio
- text

Vietnamese:

> hình ảnh, âm thanh, văn bản

### Important Meaning

The 2026 competition is not only about finding multimedia items. It also emphasizes:

- intelligent virtual assistant behavior
- advanced analysis
- information retrieval
- large-scale multimedia data
- Vietnamese-specific language, audio, and image data
- Large Vision Language Models
- generative AI
- intelligent interaction between modules/systems

---

## 9. 2025 vs 2026 Topic Difference

### AI Challenge 2025 Topic

**Virtual assistant supports Retrieval from a large multimedia database**

Main implication:

- virtual assistant supports retrieval
- focus is primarily on retrieving information from a large multimedia database

Simplified interpretation:

```text
Query → Retrieval → Candidate result
```

### AI Challenge 2026 Topic

**Intelligent virtual Assistant for advanced Analysis and Information retrieval from large-scale Multimedia data**

Main implication:

- intelligent assistant
- advanced analysis
- information retrieval
- large-scale multimedia data
- not only retrieval, but also analysis and answer/evidence handling

Simplified interpretation:

```text
Query → Understand task → Analyze multimedia evidence → Retrieve information → Return answer or target item
```

### Practical Difference

2025:

> Find relevant information from a large multimedia database.

2026:

> Analyze multimedia data and retrieve information or answers from large-scale multimedia data.

This distinction is important for interpreting the expected tasks.

---

## 10. Official Problem Description

Participants must develop a solution for:

> An intelligent virtual assistant that supports advanced analysis and information retrieval from large-scale multimedia data.

The multimedia data may include:

- videos
- images (frame, keyframes, etc.)
- audio (speech, sound, etc.)
- text (description, caption, etc.)
- metadata (timestamp, location, user info, etc.)

The competition is organized as a scientific challenge, similar to international challenges (LifeLog search, video browser showdown, life-logging, life-summarization, etc.) that seek effective solutions for new and important problems.

Vietnamese source meaning:

> Cuộc thi được tổ chức theo hình thức cuộc thi khoa học, tương tự các cuộc thi (challenge) thường được tổ chức trên thế giới nhằm tìm kiếm các giải pháp hiệu quả cho các vấn đề mới đang được quan tâm nhằm phục vụ cuộc sống.

---

## 11. Related International Challenge Formats

The 2026 problem format is officially described as similar to:

1. **Lifelog Search Challenge**
   - Abbreviation: **LSC**

2. **Video Browser Showdown**
   - Abbreviation: **VBS**

Vietnamese source meaning:

> Thể thức tương tự cuộc thi quốc tế Lifelog Search Challenge (LSC) và Video Browser Showdown (VBS).

This reference is important because it suggests the competition may involve:

- interactive multimedia retrieval
- known-item search
- visual search
- question answering
- temporal reasoning
- real-time or near-real-time task solving
- possible live judging conditions

However, exact 2026 rules must still be confirmed from official announcements.

---

## 12. Official Competition Modes

The 2026 competition will move toward **2 forms/modes**.

### 12.1 Traditional Mode

Official description:

> Người dùng sẽ sử dụng công cụ Trợ lý ảo thông minh của nhóm mình để xử lý truy vấn thông tin từ kho dữ liệu multimedia.

English meaning:

> A user uses the team’s intelligent virtual assistant tool to process information retrieval queries from the multimedia database.

Interpretation:

- There is a human user/operator.
- The operator uses the team’s tool.
- The tool processes queries over the multimedia data.
- The output is submitted according to competition rules.

### 12.2 Automatic Mode

Official description:

> Hội thi sẽ thử nghiệm đưa thêm hình thức thi tự động giữa các Trợ lý ảo thông minh của các nhóm.

English meaning:

> The competition will experiment with adding an automatic competition mode between intelligent virtual assistants from different teams.

Interpretation:

- The assistant may need to process tasks automatically.
- Human intervention may be limited or disallowed in this mode.
- The exact protocol is not yet fully specified.
- This is described as an experimental direction for 2026.

### Important Distinction

Competition modes are **not query types**.

The same query/task types may appear in:

- traditional human-in-the-loop mode
- automatic assistant-vs-assistant mode

---

## 13. Known Competition Rounds / Phases

The official public information gives the following major phases.

### 13.1 Registration Phase

Expected period:

- from competition launch
- until June 15, 2026

Purpose:

- teams register through the official portal

Known output:

- team registration information

No technical submission format is specified for this phase.

### 13.2 Training Phase

Expected period:

- June–July 2026

Official description:

> Sau khi đăng ký tham dự Cuộc thi, thí sinh được tập huấn kiến thức về các nội dung theo chủ đề cuộc thi.

English meaning:

> After registering, participants receive training on knowledge related to the competition topic.

Purpose:

- participants receive topic-specific training
- organizers may explain rules, data, query types, and task format

Known output:

- no official competition output stated yet

### 13.3 Preliminary Requirement Announcement

Expected date:

- June 25, 2026

Purpose:

- organizers announce the content and requirements for the preliminary round

This is an important milestone because the exact task format, input format, output format, dataset details, and scoring rules may be clarified here.

### 13.4 Preliminary Round

Expected period:

- August 2026

Known purpose:

- competition round before the final
- likely used to select teams for the final round

Known constraints:

- exact input and output format are currently not public in detail
- exact scoring rules are currently not public in detail

Likely output categories:

- target item submission
- answer text
- timestamp or segment
- structured result file or online submission

But these are not official yet and must be treated as **TBD**.

### 13.5 Preliminary Result Announcement

Expected date:

- August 30, 2026

Purpose:

- announce teams selected for the final round

Known output:

- finalist list

### 13.6 Final Round

Expected period:

- September 12–26, 2026

Known purpose:

- final competition round
- likely includes live or interactive use of team systems
- may include traditional mode and/or automatic mode

Known constraints:

- exact scoring protocol is not fully public yet
- exact input/output protocol is not fully public yet
- exact allowed hardware/network/API restrictions are not fully public yet

### 13.7 Award Ceremony

Expected time:

- October 2026

Purpose:

- competition closing
- award distribution
- possible follow-up academic and application opportunities

---

## 14. Official / Expected Task Types

Based on the information provided by the user about the competition and its 2025/2026 direction, the expected main task/query types should be modeled as **4 primary types**:

1. **TKIS**
2. **VKIS**
3. **Q&A**
4. **TRAKE**

These should be treated as the main task categories unless official 2026 documents later define a different set.

---

## 15. Task Type 1 — TKIS

### Full Name

**Textual Known-Item Search**

### Short Name

**TKIS**

### Input

A textual query describing a target item, scene, event, moment, or segment in the multimedia database.

The query may be in:

- Vietnamese
- English
- potentially mixed Vietnamese-English

Exact language constraints are **TBD**.

### Expected User Goal

Find the exact or best-matching known item in the multimedia database based on the textual description.

### Typical Input Example

```text
Find the scene where a man wearing a red shirt is standing next to a bus.
```

Vietnamese example:

```text
Tìm cảnh một người đàn ông mặc áo đỏ đứng cạnh một chiếc xe buýt.
```

### Possible Expected Output

The official format is TBD, but likely output may include one or more of:

- `video_id`
- `frame_id`
- `segment_id`
- `timestamp`
- `timestamp_start`
- `timestamp_end`

### Recommended Internal Normalized Output

```json
{
  "task_type": "tkis",
  "query_id": "q001",
  "video_id": "video_001",
  "frame_id": "video_001_frame_000123",
  "segment_id": "video_001_seg_000123",
  "timestamp": 123.45,
  "timestamp_start": 123.00,
  "timestamp_end": 128.00,
  "answer_text": null,
  "confidence": 0.86,
  "evidence": {
    "caption": "A man wearing a red shirt is standing next to a bus.",
    "ocr_text": null,
    "asr_text": null
  }
}
```

### Notes

For TKIS, the answer is usually a target item/location in the dataset, not a long natural-language answer.

---

## 16. Task Type 2 — VKIS

### Full Name

**Visual Known-Item Search**

May also appear conceptually as:

- Image Known-Item Search
- Video Known-Item Search
- Visual KIS
- Image/Video KIS

### Short Name

**VKIS**

### Input

A visual query or clue, such as:

- an image
- a video clip
- a frame
- a visual example shown during the competition
- possibly a description of a visual clue if direct visual input is not allowed

Exact input protocol is **TBD**.

### Expected User Goal

Find the matching or best-matching visual item in the multimedia database.

### Typical Input Example

```text
The judge shows a short video clip of a woman standing near a white car. Find the corresponding segment in the database.
```

Vietnamese example:

```text
Ban giám khảo chiếu một đoạn video ngắn có một người phụ nữ đứng gần xe màu trắng. Hãy tìm đoạn tương ứng trong cơ sở dữ liệu.
```

### Possible Expected Output

The official format is TBD, but likely output may include one or more of:

- `video_id`
- `frame_id`
- `segment_id`
- `timestamp`
- `timestamp_start`
- `timestamp_end`

### Recommended Internal Normalized Output

```json
{
  "task_type": "vkis",
  "query_id": "q002",
  "video_id": "video_014",
  "frame_id": "video_014_frame_000456",
  "segment_id": "video_014_seg_000456",
  "timestamp": 456.78,
  "timestamp_start": 454.00,
  "timestamp_end": 461.00,
  "answer_text": null,
  "confidence": 0.91,
  "evidence": {
    "caption": "A woman is standing near a white car.",
    "visual_match_description": "The retrieved frame visually matches the shown clue."
  }
}
```

### Important TBD Constraints

The official rules must clarify:

- whether teams are allowed to directly input the shown image/video into their system
- whether teams are forbidden from capturing the visual query
- whether the operator must manually describe the visual clue
- whether only the final ID/timestamp is submitted

---

## 17. Task Type 3 — Q&A

### Full Name

**Question Answering over Multimedia**

### Short Name

**Q&A**

### Input

A natural-language question whose answer must be derived from the multimedia database.

The evidence may come from:

- image/video content
- spoken audio
- transcript
- OCR text
- metadata
- captions
- temporal context

### Expected User Goal

Answer a question using evidence from the multimedia data.

### Typical Input Example

```text
What is the main topic discussed by the speaker standing in front of the blue screen?
```

Vietnamese example:

```text
Người đang phát biểu trước màn hình màu xanh đang nói về chủ đề gì?
```

### Possible Expected Output

The official format is TBD, but likely output may include one or more of:

- `answer_text`
- `video_id`
- `segment_id`
- `timestamp_start`
- `timestamp_end`
- supporting evidence

### Recommended Internal Normalized Output

```json
{
  "task_type": "qa",
  "query_id": "q003",
  "video_id": "video_021",
  "segment_id": "video_021_seg_000087",
  "timestamp_start": 87.20,
  "timestamp_end": 104.50,
  "timestamp": 87.20,
  "answer_text": "The speaker is discussing digital transformation in education.",
  "confidence": 0.82,
  "evidence": {
    "caption": "A speaker is presenting on stage in front of a blue screen.",
    "ocr_text": "DIGITAL TRANSFORMATION IN EDUCATION",
    "asr_text": "chuyển đổi số trong giáo dục..."
  }
}
```

### Important TBD Constraints

The official rules must clarify:

- whether the answer must be free text
- whether the answer must include evidence
- whether a timestamp is mandatory
- whether exact wording matters
- whether multiple answers are accepted
- whether answer scoring is automatic or human-judged

---

## 18. Task Type 4 — TRAKE

### Name

**TRAKE**

The user-provided context identifies TRAKE as one of the four expected task types.

The exact official expansion/definition of TRAKE for AI Challenge 2026 is not yet specified in the provided materials.

### Working Interpretation

TRAKE should be treated as a temporal and/or reasoning-oriented task involving:

- event sequence
- before/after relationships
- transitions
- temporal context
- reasoning across one or more segments
- possibly tracking an event or entity across time

### Input

A query involving temporal or reasoning relations over multimedia data.

### Expected User Goal

Identify a target event, segment, timestamp, or answer by reasoning over temporal/multimodal evidence.

### Typical Input Example

```text
What happens after the person enters the building?
```

Vietnamese example:

```text
Sau khi người đó bước vào tòa nhà thì chuyện gì xảy ra tiếp theo?
```

Another example:

```text
Find the segment immediately before the scene where the speaker walks onto the stage.
```

Vietnamese:

```text
Tìm đoạn ngay trước cảnh người phát biểu bước lên sân khấu.
```

### Possible Expected Output

The official format is TBD, but likely output may include one or more of:

- `video_id`
- `segment_id`
- `timestamp`
- `timestamp_start`
- `timestamp_end`
- `answer_text`
- temporal evidence

### Recommended Internal Normalized Output

```json
{
  "task_type": "trake",
  "query_id": "q004",
  "video_id": "video_044",
  "segment_id": "video_044_seg_000501",
  "timestamp_start": 501.00,
  "timestamp_end": 519.00,
  "timestamp": 501.00,
  "answer_text": "After entering the building, the person walks to the reception desk.",
  "confidence": 0.76,
  "evidence": {
    "previous_event": "The person enters the building.",
    "target_event": "The person walks to the reception desk.",
    "temporal_relation": "target event occurs after anchor event"
  }
}
```

### Important TBD Constraints

The official rules must clarify:

- the exact definition of TRAKE
- whether TRAKE requires returning a segment, answer text, or both
- whether temporal evidence must be included
- whether the target is always in the same video
- whether multi-step reasoning is required

---

## 19. Supporting Capabilities Mentioned by the Official Theme

The following are not official query types by themselves. They are capabilities or evidence sources implied by the official theme.

### 19.1 Image / Video Understanding

Relevant because the official task involves multimedia data including images.

### 19.2 Audio Understanding

Relevant because the official task explicitly mentions audio data.

### 19.3 Text Understanding

Relevant because the official task explicitly mentions text data.

### 19.4 Vietnamese-Specific Data Processing

The official description encourages solutions for data specific to Vietnam, including:

- language
- audio
- images

Vietnamese source meaning:

> xử lý dữ liệu đặc thù tại Việt Nam (ngôn ngữ, âm thanh, hình ảnh)

### 19.5 Large Vision Language Models

The official description encourages using:

- Large Vision Language Models
- abbreviation: LVLM

### 19.6 Generative AI

The official description encourages using:

- generative AI

### 19.7 Intelligent Interaction Between Modules/Systems

The official description encourages:

- intelligent interaction between modules/systems

This is a topic-level expectation, not a specified implementation requirement.

---

## 20. Expected Input Categories

The exact 2026 input protocol is TBD. Based on the official theme and expected task types, the system should be prepared to receive or reason about the following input categories.

### 20.1 Text Query

Used for:

- TKIS
- Q&A
- TRAKE
- possibly textual descriptions in VKIS if visual input is not directly allowed

Example:

```text
Find the scene where a speaker discusses artificial intelligence in education.
```

### 20.2 Visual Query

Used for:

- VKIS

Possible forms:

- image
- video clip
- keyframe
- visual clue shown by judges

Exact protocol is TBD.

### 20.3 Multimedia Database

The system will operate over a large-scale multimedia dataset.

Official modalities:

- image
- audio
- text

Possible dataset components, based on past AI Challenge patterns and the 2026 theme:

- videos
- keyframes
- images
- metadata
- audio
- transcripts
- OCR text
- captions/descriptions
- embeddings or features

Only the modalities explicitly stated for 2026 are confirmed:

- images
- audio
- text

The rest are possible and must be confirmed from official dataset release or training sessions.

### 20.4 Official Submission Interface

TBD.

Possible forms:

- web form
- scoring server
- CSV file
- JSON file
- API call
- competition platform

No final official 2026 submission protocol is currently included in the provided materials.

---

## 21. Expected Output Categories

The exact official output format is TBD. The system context should preserve all possible answer fields until official rules are known.

### 21.1 Target Item Output

Likely used for:

- TKIS
- VKIS
- some TRAKE tasks

Possible fields:

```json
{
  "video_id": "string",
  "frame_id": "string_or_null",
  "segment_id": "string_or_null",
  "timestamp": "number_or_null",
  "timestamp_start": "number_or_null",
  "timestamp_end": "number_or_null"
}
```

### 21.2 Textual Answer Output

Likely used for:

- Q&A
- some TRAKE tasks

Possible fields:

```json
{
  "answer_text": "string",
  "video_id": "string_or_null",
  "timestamp_start": "number_or_null",
  "timestamp_end": "number_or_null"
}
```

### 21.3 Evidence Output

Possibly required for:

- Q&A
- TRAKE
- advanced analysis tasks

Possible fields:

```json
{
  "evidence": {
    "video_id": "string",
    "timestamp_start": "number",
    "timestamp_end": "number",
    "caption": "string_or_null",
    "ocr_text": "string_or_null",
    "asr_text": "string_or_null",
    "visual_description": "string_or_null"
  }
}
```

### 21.4 Confidence Output

Not confirmed officially.

Useful internal field:

```json
{
  "confidence": 0.0
}
```

Whether confidence should be submitted officially is TBD.

---

## 22. Universal Internal Answer Object

Until official output rules are known, all tasks should be represented internally using a universal answer object.

```json
{
  "query_id": "string",
  "query_text": "string",
  "task_type": "tkis | vkis | qa | trake",
  "video_id": "string_or_null",
  "frame_id": "string_or_null",
  "segment_id": "string_or_null",
  "timestamp": "number_or_null",
  "timestamp_start": "number_or_null",
  "timestamp_end": "number_or_null",
  "answer_text": "string_or_null",
  "confidence": "number_or_null",
  "evidence": {
    "caption": "string_or_null",
    "ocr_text": "string_or_null",
    "asr_text": "string_or_null",
    "visual_description": "string_or_null",
    "temporal_relation": "string_or_null"
  }
}
```

This object is not claimed to be the official output format. It is a normalized context object that can be adapted once the official format is announced.

---

## 23. In-Competition Process

This section describes the expected operational process during the competition. Exact official procedures are TBD.

### 23.1 Before a Competition Session

Expected preparation steps:

1. Confirm team identity and registered division.
2. Confirm official dataset or competition environment.
3. Confirm scoring/submission interface.
4. Confirm allowed resources.
5. Confirm whether the current session is traditional mode or automatic mode.
6. Confirm whether queries are text, visual, Q&A, TRAKE, or mixed.
7. Confirm output format for the session.
8. Confirm whether wrong submissions are penalized.
9. Confirm whether multiple submissions are allowed.
10. Confirm time limits.

### 23.2 When a Query Is Given

For each query:

1. Record or receive the query.
2. Identify task type:
   - TKIS
   - VKIS
   - Q&A
   - TRAKE
3. Identify expected output:
   - target video/frame/timestamp
   - answer text
   - segment range
   - evidence
4. Process the query using the available competition mode:
   - human-in-the-loop traditional mode
   - automatic mode
5. Produce a candidate answer.
6. Verify the answer according to the task type.
7. Submit according to official protocol.

### 23.3 Traditional Mode Process

In traditional mode:

1. A human user/operator receives or reads the query.
2. The user uses the team’s intelligent virtual assistant tool.
3. The tool processes the query over the multimedia database.
4. The user selects or confirms the answer.
5. The team submits the answer through the official channel.

Known from official description:

> The user uses the team’s intelligent virtual assistant tool to process information retrieval queries from the multimedia database.

### 23.4 Automatic Mode Process

In automatic mode:

1. The assistant receives the query or task.
2. The assistant processes the query automatically.
3. The assistant returns an answer.
4. The answer is evaluated against other assistants or official scoring rules.

Known from official description:

> The competition will experiment with automatic competition between intelligent virtual assistants from different teams.

Exact automatic protocol is TBD.

### 23.5 After Submission

Possible outcomes:

- accepted answer
- rejected answer
- scored answer
- time-based score
- penalty for wrong attempt
- opportunity to resubmit

These outcomes are not confirmed for 2026 and must be clarified from official rules.

---

## 24. Sample Queries by Task Type

These are illustrative examples only. They are not official 2026 queries.

### 24.1 TKIS Sample Queries

English:

```text
Find the scene where a man in a red shirt stands next to a bus.
```

```text
Find the moment when a group of students are sitting in a classroom and looking at a large screen.
```

```text
Find the video segment showing a person holding a microphone on a stage.
```

Vietnamese:

```text
Tìm cảnh một người đàn ông mặc áo đỏ đứng cạnh xe buýt.
```

```text
Tìm khoảnh khắc một nhóm học sinh đang ngồi trong lớp và nhìn lên màn hình lớn.
```

```text
Tìm đoạn video có một người đang cầm micro trên sân khấu.
```

Expected output type:

```json
{
  "task_type": "tkis",
  "video_id": "string",
  "timestamp": "number",
  "frame_id": "string_or_null",
  "segment_id": "string_or_null"
}
```

### 24.2 VKIS Sample Queries

English:

```text
The judge shows an image of a woman standing near a white car. Find the matching segment.
```

```text
The judge shows a short clip of a speaker in front of a blue screen. Find the corresponding video moment.
```

Vietnamese:

```text
Ban giám khảo hiển thị một hình ảnh có người phụ nữ đứng gần xe màu trắng. Hãy tìm đoạn tương ứng.
```

```text
Ban giám khảo chiếu một đoạn ngắn có người phát biểu trước màn hình màu xanh. Hãy tìm khoảnh khắc tương ứng trong video.
```

Expected output type:

```json
{
  "task_type": "vkis",
  "video_id": "string",
  "timestamp": "number",
  "frame_id": "string_or_null",
  "segment_id": "string_or_null"
}
```

### 24.3 Q&A Sample Queries

English:

```text
What is the speaker talking about in the segment where the slide says "Digital Transformation"?
```

```text
What organization name appears on the banner behind the speaker?
```

```text
What is the main topic discussed in the video segment showing a classroom?
```

Vietnamese:

```text
Người phát biểu đang nói về nội dung gì trong đoạn có slide ghi "Chuyển đổi số"?
```

```text
Tên tổ chức nào xuất hiện trên banner phía sau người phát biểu?
```

```text
Chủ đề chính được thảo luận trong đoạn video có cảnh lớp học là gì?
```

Expected output type:

```json
{
  "task_type": "qa",
  "answer_text": "string",
  "video_id": "string_or_null",
  "timestamp_start": "number_or_null",
  "timestamp_end": "number_or_null",
  "evidence": "object_or_null"
}
```

### 24.4 TRAKE Sample Queries

English:

```text
What happens immediately after the person enters the building?
```

```text
Find the segment before the speaker walks onto the stage.
```

```text
After the slide about smart city appears, what is the next visible event?
```

Vietnamese:

```text
Điều gì xảy ra ngay sau khi người đó bước vào tòa nhà?
```

```text
Tìm đoạn ngay trước cảnh người phát biểu bước lên sân khấu.
```

```text
Sau khi slide về đô thị thông minh xuất hiện, sự kiện tiếp theo nhìn thấy là gì?
```

Expected output type:

```json
{
  "task_type": "trake",
  "answer_text": "string_or_null",
  "video_id": "string_or_null",
  "timestamp_start": "number_or_null",
  "timestamp_end": "number_or_null",
  "temporal_relation": "string_or_null"
}
```

---

## 25. Awards

### Award Types

The competition includes the following award levels:

- First Prize
- Second Prize
- Third Prize
- Consolation Prize

Vietnamese:

- Giải nhất
- Giải nhì
- Giải ba
- Giải khuyến khích

### Award Form

Awards may include:

- cup
- cash prize
- certificate from the organizing committee

Vietnamese:

> Cúp, tiền thưởng, giấy khen của BTC Hội thi.

### Number of Awards

The number of awards will be decided based on:

- proposal from the judging council
- decision of the organizing committee

Vietnamese source meaning:

> Số lượng giải thưởng sẽ căn cứ theo đề xuất của Hội đồng giám khảo và Ban Tổ chức sau khi xem xét, quyết định.

---

## 26. Benefits for Participants / Winning Teams

### Training Benefit

All registered participants can join specialized training sessions throughout the competition.

Purpose:

- provide practical experience in solving AI problems
- provide knowledge related to the competition topic

### Benefits for High-Performing Teams

High-performing teams may receive the following opportunities:

1. Their methods may be reviewed by domestic and international experts.
2. Selected methods may be invited for presentation at a Special Session on **Lifelog and Multimedia Event Retrieval** at **SoICT 2026**.
3. Selected methods may be published in the conference proceedings published by **ACM**.
4. Some promising, unique, and high-performing methods may be selected for submission to a Special Issue of **Multimedia Tools and Applications**.
5. Teams may be introduced to experts and scientists for further guidance.
6. Teams may be supported in connecting their algorithms/solutions to units implementing e-government and smart city systems.
7. Teams may be supported in registering useful solutions or incubating potential products.
8. Participants may join visits to IT and AI companies in Ho Chi Minh City during the competition.

### SoICT Mention

Official text refers to:

> The 15th International Symposium on Information and Communication Technology (SoICT 2026)

### Publication Mention

Official text refers to:

- ACM proceedings
- Multimedia Tools and Applications
- Q1 journal group

These are benefits, not task requirements.

---

## 27. Known Constraints

### Confirmed Constraints

| Constraint | Status |
|---|---|
| Team size maximum 5 members | Confirmed |
| Two divisions: A and B | Confirmed |
| Division B may use organizer-provided tools | Confirmed |
| Registration through official portal | Confirmed |
| 2026 task involves multimedia data | Confirmed |
| Modalities include images, audio, text | Confirmed |
| Theme involves intelligent virtual assistant | Confirmed |
| Theme involves advanced analysis and information retrieval | Confirmed |
| Similar format to LSC and VBS | Confirmed |
| Two competition modes: traditional and automatic experimental mode | Confirmed |
| Training sessions after registration | Confirmed |

### Unknown / TBD Constraints

| Constraint | Status |
|---|---|
| Exact dataset format | TBD |
| Whether keyframes are provided | TBD |
| Whether embeddings are provided | TBD |
| Whether transcripts are provided | TBD |
| Whether OCR is provided | TBD |
| Whether external APIs are allowed | TBD |
| Whether internet is allowed during final round | TBD |
| Whether cloud servers are allowed | TBD |
| Hardware limits | TBD |
| Exact scoring formula | TBD |
| Wrong submission penalty | TBD |
| Number of submissions per query | TBD |
| Query time limit | TBD |
| Exact official output format | TBD |
| Whether visual query capture/input is allowed | TBD |
| Whether evidence must be submitted | TBD |
| Whether automatic mode affects official ranking or is experimental only | TBD |
| Whether Q&A answers are free text or structured | TBD |
| Exact definition of TRAKE in 2026 | TBD |

---

## 28. Questions to Clarify During Training

These questions should be asked during official training or rule clarification.

### Dataset

1. What exactly is included in the dataset?
2. Are videos provided?
3. Are keyframes provided?
4. Are image files provided separately?
5. Are audio files provided separately?
6. Are metadata files provided?
7. Are embeddings/features provided?
8. Are transcripts or ASR outputs provided?
9. Is OCR text provided?
10. Are captions/descriptions provided?

### Inputs

1. What query types are officially used in 2026?
2. Are the official query types TKIS, VKIS, Q&A, and TRAKE?
3. What is the exact definition of TRAKE?
4. Are queries in Vietnamese, English, or both?
5. Will visual queries be shown as images or video clips?
6. Are teams allowed to directly input image/video query data into their system?
7. Are teams allowed to capture or screenshot visual queries?

### Outputs

1. What is the official output format for TKIS?
2. What is the official output format for VKIS?
3. What is the official output format for Q&A?
4. What is the official output format for TRAKE?
5. Is timestamp required?
6. Is frame ID required?
7. Is segment ID required?
8. Is answer text required?
9. Is supporting evidence required?
10. Are multiple candidates allowed?
11. Is confidence score submitted or ignored?

### Rounds and Scoring

1. What is the preliminary round format?
2. What is the final round format?
3. Will the final round include traditional mode?
4. Will the final round include automatic mode?
5. Is automatic mode officially scored or experimental only?
6. Is there a time limit per query?
7. Are wrong submissions penalized?
8. Are repeated submissions allowed?
9. How is time used in scoring?
10. Is there a scoring server?

### Runtime Constraints

1. Are external APIs allowed?
2. Is internet access allowed?
3. Are cloud servers allowed?
4. Must the system run locally?
5. Are GPUs allowed?
6. Are there model size restrictions?
7. Are pretrained models allowed?
8. Are generative AI models allowed?
9. Are LVLMs allowed?
10. Must methods be disclosed?

---

## 29. Minimal Context Summary for Future Agents

The competition is **AI Challenge 2026** in Ho Chi Minh City.

Participants build an:

> Intelligent virtual assistant for advanced analysis and information retrieval from large-scale multimedia data.

The data modalities explicitly mentioned are:

- images
- audio
- text

The problem is similar to:

- Lifelog Search Challenge
- Video Browser Showdown

Expected main task types from user-provided context:

- TKIS
- VKIS
- Q&A
- TRAKE

The competition has two modes:

- traditional human-in-the-loop mode
- experimental automatic assistant-vs-assistant mode

The official output format is not yet fully known.

The assistant should be prepared to output:

- target video/frame/segment/timestamp for search tasks
- answer text and evidence for Q&A tasks
- segment/time/answer for TRAKE tasks

Do not assume any exact official schema until the organizers publish the preliminary/final round requirements.

---

## 30. Final Instruction for Coding/Design Agents

When using this file as context, do not treat it as a system design.

This file only describes:

- competition background
- official constraints
- topic
- task types
- rounds
- expected inputs
- expected outputs
- known unknowns
- sample queries

A separate design step is required to propose:

- architecture
- data model
- APIs
- UI
- retrieval strategy
- agent strategy
- evaluation plan
- implementation roadmap
