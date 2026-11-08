"""Write the synthetic stress set: short hand-written calls for labels and timing phrases
that never appear in the 50 supplied calls (Invalid Lead reasons, Do Not Contact, Online,
Rescheduled, Unable to Assess, refusal reversal, callback amendment, offset-8 booking, ...).

Gold labels were written from the policy BEFORE any model run. These records are a
robustness check only; they are never used as prompt examples.

Usage: python scripts/make_synthetic.py [out_dir]
"""
import json
import sys
from pathlib import Path

A, C = "Agent", "Customer"


def t(*turns):
    return "\n".join(f"{s}: {u}" for s, u in turns)


RECORDS = [
    ("SYN-01", "2026-10-13T11:05:12+05:30", ("Invalid Lead", "Wrong Contact", "Not Qualified", None), t(
        (A, "Hello, am I speaking with Mr. Rakesh? I'm calling from Aster Vale Pain Clinic about your knee pain enquiry."),
        (C, "No, there is no Rakesh here. This is a shop number."),
        (A, "Sir, we received an enquiry from this number yesterday for knee pain."),
        (C, "No, no, nobody here made any enquiry. Nobody here has any knee problem either. Wrong number."),
        (A, "Okay sir, sorry for the disturbance."),
        (C, "It's okay."))),
    ("SYN-02", "2026-10-14T15:20:00+05:30", ("Invalid Lead", "No Pain Need", "Not Qualified", None), t(
        (A, "Hello ma'am, I'm Riya from Aster Vale Care. You had filled a form on our page. Tell me, what problem are you facing?"),
        (C, "Yes, I filled it. I wanted a hair fall treatment. Do you do hair transplant?"),
        (A, "Ma'am, we are a pain clinic. Do you have any pain, back, knee, neck, anything?"),
        (C, "No, no pain at all. I'm completely fine, just hair fall. Nobody at home has pain also."),
        (A, "Okay ma'am, then our clinic won't be able to help with that."),
        (C, "Okay, thank you."))),
    ("SYN-03", "2026-10-15T10:00:00+05:30", ("Invalid Lead", "Policy Exclusion", "Not Qualified", None), t(
        (A, "Hello, Aster Vale Pain Clinic, I'm Kabir. You enquired for pain treatment?"),
        (C, "Yes, it's for my son. He has knee pain after football for two weeks."),
        (A, "How old is your son, ma'am?"),
        (C, "He is twelve years old."),
        (A, "Ma'am, our clinic sees patients who are fifteen years or older. For a twelve-year-old we cannot book a consultation. Please consult a paediatric orthopaedic doctor."),
        (C, "Oh, okay. Fine, thank you."))),
    ("SYN-04", "2026-10-16T17:45:00+05:30", ("Invalid Lead", "Test Enquiry", "Not Qualified", None), t(
        (A, "Hello, Aster Vale Care, how can I help you?"),
        (C, "Hi, this is Priya from the internal CRM team. This is just a test lead, we're checking the new dialer. Please mark it as test."),
        (A, "Okay Priya, noted, I'll mark this enquiry as a test."),
        (C, "Thanks, bye."))),
    ("SYN-05", "2026-10-17T12:10:00+05:30", ("Invalid Lead", "Outside Service Area", "Not Qualified", None), t(
        (A, "Hello sir, Aster Vale Pain Clinic. You enquired about back pain?"),
        (C, "Yes, I have lower back pain for a year. But I live permanently in Toronto, I've been settled there for fifteen years."),
        (A, "Sir, our clinics are only in India. Will you be visiting India anytime?"),
        (C, "No, I'm not coming to India, not this year or next year."),
        (A, "We can do an online video consultation with our doctor."),
        (C, "No, I don't want online. For pain I need a doctor to examine me physically. Online is of no use to me."),
        (A, "Okay sir, understood."))),
    ("SYN-06", "2026-10-12T18:30:00+05:30", ("Not Interested", "Do Not Contact", "Low", None), t(
        (A, "Hello ma'am, Aster Vale Care. You enquired for your back pain?"),
        (C, "Yes, I have back pain for six months."),
        (A, "Our doctor can see you this week. Shall I call you tomorrow at 5 to fix a time?"),
        (C, "Okay."),
        (A, "Also, the consultation is 1000 rupees, valid for 15 days."),
        (C, "Actually, you people have called me four times already. Please don't call me again. Remove my number from your list."),
        (A, "Ma'am, I was only..."),
        (C, "No, please, do not call me. I'm not interested."))),
    ("SYN-07", "2026-10-13T09:40:00+05:30", ("Appointment Scheduled", "Online Consultation", "High", None), t(
        (A, "Hello sir, Aster Vale Care. You enquired for neck pain?"),
        (C, "Yes, neck pain for three months. But I'm in Jaipur now for work for two months."),
        (A, "No problem, sir. We can do a video consultation with Dr. Naman. The doctor will see your reports online."),
        (C, "That works. When?"),
        (A, "Thursday, the 15th, at 6 PM on video call. Shall I book it?"),
        (C, "Yes, book it for Thursday 6 PM."),
        (A, "Done sir, your online consultation is confirmed for Thursday 6 PM. I'll send the video link on WhatsApp."),
        (C, "Okay, thank you."))),
    ("SYN-08", "2026-10-14T13:00:00+05:30", ("Appointment Scheduled", "Rescheduled", "High", None), t(
        (A, "Hello ma'am, Aster Vale Care. You had an appointment yesterday at 11 with Dr. Mira but you couldn't come."),
        (C, "Yes, sorry, my knee pain was bad and there was nobody to drop me. I still want to come."),
        (A, "No problem. Shall I move your appointment to Friday, the 16th, at 12:30?"),
        (C, "Yes, Friday 12:30 is fine. Please change it."),
        (A, "Done ma'am, your appointment is rescheduled to Friday 12:30 PM."),
        (C, "Okay, thank you."))),
    ("SYN-09", "2026-10-15T16:00:00+05:30", ("Unable to Assess", "Incomplete Conversation", "Not Assessable", None), t(
        (A, "Hello?"),
        (A, "Hello, am I audible?"),
        (C, "Hello... who... [noise]"),
        (A, "Sir, I'm calling from Aster Vale..."),
        (C, "[inaudible]"),
        (A, "Hello? Hello?"))),
    ("SYN-10", "2026-10-16T11:15:00+05:30", ("Appointment Scheduled", "Clinic Visit", "High", None), t(
        (A, "Hello ma'am, Aster Vale Care, about your shoulder pain enquiry."),
        (C, "I'm not interested, your treatment is too expensive."),
        (A, "Ma'am, the consultation is only 1000 rupees and procedures have zero-cost EMI. The doctor will examine you first."),
        (C, "EMI is there? Okay, then that's manageable. My shoulder pain is really bad for four months."),
        (A, "Shall I book you with the doctor tomorrow?"),
        (C, "Okay fine, book me tomorrow at 4."),
        (A, "Done, your consultation is booked for tomorrow, Saturday, at 4 PM at Cedar Square."),
        (C, "Okay, I'll come."))),
    ("SYN-11", "2026-10-17T14:20:00+05:30", ("Follow-up Required", "Family Discussion", "Medium", "2026-10-20T18:00:00+05:30"), t(
        (A, "Hello sir, Aster Vale Care. You enquired about sciatica?"),
        (C, "Yes, the pain goes down my leg for two months. I want the treatment but my wife decides these things, I need to discuss with her first."),
        (A, "Sure. When should I call you back?"),
        (C, "Call me Monday."),
        (A, "Okay, Monday morning?"),
        (C, "No, make it Tuesday evening. Monday I'm busy the whole day."),
        (A, "Okay sir, Tuesday evening I'll call you."),
        (C, "Okay."))),
    ("SYN-12", "2026-10-12T12:00:00+05:30", ("Appointment Scheduled", "Clinic Visit", "Medium", None), t(
        (A, "Hello ma'am, Aster Vale Care. You enquired about knee pain?"),
        (C, "Yes, for my mother, she is 64, knee pain for a year."),
        (A, "The doctor is available this week. When would you like to come?"),
        (C, "Not this week. Book it for the 20th, at 11 in the morning."),
        (A, "Done ma'am, consultation confirmed on the 20th at 11 AM."),
        (C, "Okay, thank you."))),
    ("SYN-13", "2026-10-18T10:30:00+05:30", ("Not Interested", "Explicit Refusal", "Low", None), t(
        (A, "Hello sir, Aster Vale Care. You enquired about your back pain."),
        (C, "Yes, but I've read about your procedures. I don't want any injection-based treatment."),
        (A, "Sir, not all are injections, the doctor will decide after examination."),
        (C, "No, I have decided. I'm not interested in your clinic's treatment. Final."),
        (A, "Okay sir."))),
    ("SYN-14", "2026-10-15T11:30:45+05:30", ("Follow-up Required", "Specific Callback", "Medium", "2026-10-15T13:30:45+05:30"), t(
        (A, "Hello ma'am, Aster Vale Care. You enquired about shoulder pain?"),
        (C, "Yes, my right shoulder hurts for three months. I want to know about the treatment."),
        (A, "Sure, I can explain the options and the doctor's timings."),
        (C, "I can't talk properly right now. Call me in two hours."),
        (A, "Sure ma'am, I'll call you in two hours."),
        (C, "Okay."))),
    ("SYN-15", "2026-10-14T17:10:00+05:30", ("Follow-up Required", "Cost Concern", "Medium", "2026-10-23T11:00:00+05:30"), t(
        (A, "Hello sir, Aster Vale Care, about your knee pain."),
        (C, "Yes, both knees pain for a year. How much does the treatment cost?"),
        (A, "Consultation is 1000 and procedures start from 10,000."),
        (C, "That's a lot for me right now. I'll have to arrange the money first."),
        (A, "When should I call you back?"),
        (C, "Call me next Friday."),
        (A, "Okay sir, next Friday I'll call you."),
        (C, "Okay."))),
    ("SYN-16", "2026-10-13T19:50:00+05:30", ("Follow-up Required", "Vague Deferral", "Medium", "2026-10-16T11:00:00+05:30"), t(
        (A, "Hello ma'am, Aster Vale Care, about your neck pain enquiry."),
        (C, "Yes, neck pain for some months."),
        (A, "The doctor can see you tomorrow or Thursday."),
        (C, "I'll think about it. Maybe call me Thursday."),
        (A, "Ma'am, I'll share the doctor's details on WhatsApp, please go through them. Thank you, have a good evening."))),
    ("SYN-17", "2026-10-18T20:15:00+05:30", ("Follow-up Required", "Current Treatment", "Medium", "2026-10-20T18:00:00+05:30"), t(
        (A, "Hello sir, Aster Vale Care. You enquired for back pain?"),
        (C, "Haan, back pain for eight months. Abhi physiotherapy chal rahi hai, it finishes this week. After that I'll decide."),
        (A, "Okay sir. Shall I call you parso?"),
        (C, "Haan, parso shaam ko call karna."),
        (A, "Theek hai sir, parso evening I'll call you."),
        (C, "Theek hai."))),
    ("SYN-18", "2026-10-12T10:05:00+05:30", ("Appointment Scheduled", "Clinic Visit", "High", "2026-10-13T11:00:00+05:30"), t(
        (A, "Hello ma'am, Aster Vale Care, about your hip pain."),
        (C, "Yes, hip pain for six months, it's getting worse."),
        (A, "Shall I book you with Dr. Mira on Wednesday, the 14th, at 3 PM?"),
        (C, "Yes, Wednesday 3 PM is fine."),
        (A, "Booked. I will also call you tomorrow at 11 to confirm the details."),
        (C, "Haan, okay."))),
]


def main(out_dir="data/synthetic"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "inputs.jsonl", "w", encoding="utf-8", newline="\n") as fi, \
         open(out / "gold.jsonl", "w", encoding="utf-8", newline="\n") as fg:
        for tid, ts, (d, s, lq, nca), text in RECORDS:
            fi.write(json.dumps({"transcript_id": tid, "call_started_at": ts, "timezone": "Asia/Kolkata", "transcript": text}) + "\n")
            fg.write(json.dumps({"transcript_id": tid, "disposition": d, "sub_disposition": s, "lead_quality": lq, "next_call_at": nca}) + "\n")
    print(f"wrote {len(RECORDS)} synthetic records to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
