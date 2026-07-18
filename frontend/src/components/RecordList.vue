<template>
  <div class="record-list">
    <h1>Answer Records</h1>
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Record</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="record in records" :key="record.id">
          <td>{{ record.date }}</td>
          <td>{{ record.answer }}</td>
          <td>{{ record.score }}</td>
        </tr>
      </tbody>
    </table>
    <div class="statistics">
      <h2>Statistics</h2>
      <p>Total Answers: {{ totalAnswers }}</p>
      <p>Average Score: {{ averageScore }}</p>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      records: [],
    };
  },
  computed: {
    totalAnswers() {
      return this.records.length;
    },
    averageScore() {
      const total = this.records.reduce((sum, record) => sum + record.score, 0);
      return total / this.totalAnswers || 0;
    },
  },
  created() {
    // Fetch records from API or any other source
    this.fetchRecords();
  },
  methods: {
    fetchRecords() {
      // Simulating an API call with static data
      this.records = [
        { id: 1, date: '2023-01-01', answer: 'Answer 1', score: 85 },
        { id: 2, date: '2023-01-02', answer: 'Answer 2', score: 90 },
        { id: 3, date: '2023-01-03', answer: 'Answer 3', score: 75 },
      ];
    },
  },
};
</script>

<style scoped>
.record-list {
  font-family: Arial, sans-serif;
  margin: 20px;
}
.table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  padding: 8px;
  border: 1px solid #ccc;
}
h1, h2 {
  color: #333;
}
</style>
