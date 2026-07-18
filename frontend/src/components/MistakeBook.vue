<template>
  <div class="mistake-book">
    <h1>My Mistakes</h1>
    <ul>
      <li v-for="(mistake, index) in mistakes" :key="index">
        <p>{{ mistake.description }}</p>
        <p>Date: {{ mistake.date }}</p>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  data() {
    return {
      mistakes: []  // this should be populated with mistake data
    };
  },
  created() {
    // fetch mistakes from an API or data source
    this.fetchMistakes();
  },
  methods: {
    fetchMistakes() {
      // logic to fetch mistakes goes here
      this.mistakes = [
        { description: 'Example mistake 1', date: '2026-01-01' },
        { description: 'Example mistake 2', date: '2026-02-01' }
      ];
    }
  }
};
</script>

<style scoped>
.mistake-book {
  font-family: Arial, sans-serif;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 5px;
}
.mistake-book h1 {
  color: #333;
}
.mistake-book ul {
  list-style-type: none;
  padding: 0;
}
.mistake-book li {
  border-bottom: 1px solid #ccc;
  padding: 10px 0;
}
</style>