// Synthetic demo documents (no real people). D1-D5 follow the team's demo script.
export const SAMPLES = [
  {
    id: 'd1', label: 'D1 · Judge example', task: 'summarize',
    text: 'My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F.',
  },
  {
    id: 'd2', label: 'D2 · Hinglish', task: 'extract',
    text: 'Mera naam Rahul Sharma hai. Main Pune mein rehta hoon. Mera PAN ABCDE1234F hai.',
  },
  {
    id: 'd3', label: 'D3 · Repeated name, no labels', task: 'summarize',
    text: 'Rahul Sharma applied for a loan. Rahul Sharma lives in Pune. Rahul Sharma submitted his PAN ABCDE1234F.',
  },
  {
    id: 'd4', label: 'D4 · Couple sharing a surname', task: 'extract',
    text: 'Loan application. Applicant Priya Nair and her husband Arjun Nair visited the branch. Priya Nair PAN ABCDE1234F, '
      + 'Aadhaar 2345 6789 0123. Business GSTIN 27ABCDE1234F1Z5. Address: 14 Shivaji Nagar, Pune 411005. '
      + 'Arjun ka passport number is K1234567.',
  },
  {
    id: 'd5', label: 'D5 · Insurance claim, all 7 types', task: 'extract',
    text: 'HEALTH INSURANCE CLAIM\nInsured: Imran Shaikh\nPatient: Fatima Shaikh (wife)\n'
      + 'Hospital: City Care Hospital, Davangere\nInsured PAN: ABCPS1234F\nInsured Aadhaar: 2341 2341 2346\n'
      + 'Voter ID: XYZ1234567\nPassport: K7654321\nEmployer GSTIN: 29ABCPS1234F1Z5\n'
      + 'Address: Plot 12, Hadadi Road, PJ Extension, Davangere 577002',
  },
  {
    id: 'd7', label: 'D7 · Messy chat: lowercase Hinglish, dotted IDs', task: 'extract',
    text: 'hi mera naam aditya hai aur me pune me reheta hu also mera adhaar no 5555-6666-7894 hai and mere dost ka '
      + 'name rahul hai aur uska adhar no 1111.2222.8888 hai. pan = ABCDE 1234 F, a.id=2345/6789/0123',
  },
  {
    id: 'd8', label: 'D8 · Raw JSON order / support payload', task: 'extract',
    text: '{"ticket": "TKT-48213", "customer_name": "rahul sharma", "address": "Flat 302, Sai Residency, Kondapur, '
      + 'Hyderabad - 500084", "city": "hyderabad", "pan": "ABCPS1234F", "aadhaar": "2341.2341.2346", '
      + '"issue": "refund not received for order 4471", "agent": "Meera"}',
  },
  {
    id: 'd6', label: 'Free-text support ticket', task: 'summarize',
    text: 'Yesterday Kavitha Subramaniam raised a ticket saying the EMI was debited twice. Her brother Venkatesh also '
      + 'holds an account. She stays near Lalbagh, Basavanagudi, Bengaluru 560004.',
  },
]
